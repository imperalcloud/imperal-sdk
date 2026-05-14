# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Single-function-call executor for ChatExtension tool-use loop.

Extracted from imperal_sdk.chat.handler in v5-27 god-file split (handler.py
717 LOC → ~425 LOC). `_execute_function` runs ONE tool_use block end-to-end:
Pydantic validation (with bounded retry feedback loop per
I-PYDANTIC-RETRY-BUDGET), guard pipeline, the actual handler call, and
return-shape normalisation. Module-private — no external callers.

Federal hooks preserved verbatim:
  * P2 Task 20 — structured error_code on PydanticValidationError + unknown
    sub-function early exit (no raw str(e) into tool_result).
  * I-PYDANTIC-RETRY-BUDGET / I-PYDANTIC-FEEDBACK-STRUCTURED — bounded retry
    with structured prose feedback piped through chat/retry helpers.
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from imperal_sdk.chat.filters import trim_tool_result
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.chat.retry import (
    format_pydantic_for_llm,
    _emit_retry_outcome,
    _RETRY_BUDGET,
    _validation_missing_field_response,
)

if TYPE_CHECKING:
    from imperal_sdk.chat.extension import ChatExtension

log = logging.getLogger(__name__)


async def _execute_function(
    chat_ext: ChatExtension, ctx, tu, action_type: str, cfg: dict,
    *,
    retry_ctx: dict | None = None,
) -> str:
    """Execute a single function call and return the tool result content string.

    When ``retry_ctx`` is provided AND the function uses a Pydantic params
    model, ``PydanticValidationError`` triggers up to ``_RETRY_BUDGET=2``
    retries with structured prose feedback to the LLM. Without ``retry_ctx``
    (or for legacy ``**kwargs`` extensions), behavior is exactly the
    pre-feature implementation.

    ``retry_ctx`` shape (passed by handle_message tool-use loop):
      client, messages, _system, _exec_cfg, _tools_for_llm,
      _tool_use_mt, _api_kwargs

    Pre-guards (UNKNOWN_SUB_FUNCTION, I-AH-1 fabricated_id) run BEFORE the
    retry loop and short-circuit with their own fc-append.

    I-AH-1 federal: fabricated-id re-check fires on every retry attempt
    (security guard remains effective across retries).

    Error contract (I-ERR-CODE-1): every failure surfaces in BOTH the
    JSON-encoded content AND ``_functions_called[-1]["result"]`` as a dict
    carrying an ``error_code`` drawn from
    :mod:`imperal_sdk.chat.error_codes`. No raw ``str(exception)`` output.
    """
    # ── Unknown sub-function early exit ──────────────────────────────────
    if tu.name not in chat_ext._functions:
        available = list(chat_ext._functions.keys())
        content = json.dumps({
            "RESULT": "ERROR",
            "error_code": "UNKNOWN_SUB_FUNCTION",
            "detail": f"'{tu.name}' not in this extension. Available: {available}",
        })
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input, "action_type": action_type,
            "success": False, "intercepted": False, "event": "",
            "result": {"error_code": "UNKNOWN_SUB_FUNCTION"},
        })
        return trim_tool_result(content, cfg["max_result_tokens"], cfg["list_truncate_items"], cfg["string_truncate_chars"])

    _func_def = chat_ext._functions[tu.name]

    # I-AH-1 L3: pre-validation shape guard — reject empirically observed
    # fabricated message_id slug shapes BEFORE Pydantic coercion so error
    # feedback to the LLM is specific ("FABRICATED_ID_SHAPE") rather than
    # generic ("VALIDATION_MISSING_FIELD"). Closes Bug-1 from prod chat
    # 2026-05-01.
    from imperal_sdk.chat.guards import check_id_shape_fabrication
    _id_rejection = check_id_shape_fabrication(tu.input or {})
    if _id_rejection is not None:
        log.warning(
            "ChatExtension I-AH-1 reject %s field=%s value=%r",
            tu.name, _id_rejection["field"], _id_rejection["value"],
        )
        content = json.dumps({"RESULT": "ERROR", **_id_rejection})
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input, "action_type": action_type,
            "success": False, "intercepted": True, "event": "",
            "result": _id_rejection,
        })
        return trim_tool_result(
            content, cfg["max_result_tokens"],
            cfg["list_truncate_items"], cfg["string_truncate_chars"],
        )

    # === Pydantic-aware retry loop (SPEC2-LLM-ARGS-QUALITY, v4.1.0) ===
    current_tu = tu
    retry_count = 0
    _ext_name = chat_ext.tool_name

    # Eligibility for retry: retry_ctx provided AND function uses a Pydantic
    # params model (legacy **kwargs paths cannot raise PydanticValidationError).
    _retry_eligible = (
        retry_ctx is not None
        and bool(_func_def._pydantic_model)
        and bool(_func_def._pydantic_param)
    )

    while True:
        try:
            # LONGRUN-V1 Component D (v4.2.13+) — declarative background-task sugar.
            # When the handler is decorated with @chat.function(background=True),
            # the SDK auto-wraps the call in ctx.background_task() and returns an
            # immediate ack envelope to the LLM. The actual handler runs detached;
            # the platform delivers its returned ActionResult as a fresh bot turn.
            if getattr(_func_def, "background", False):
                _bg_pydantic_model = _func_def._pydantic_model
                _bg_pydantic_param = _func_def._pydantic_param
                _bg_input = current_tu.input or {}
                _bg_fn = _func_def.func

                async def _bg_coro():
                    if _bg_pydantic_model and _bg_pydantic_param:
                        _mi = _bg_pydantic_model(**_bg_input)
                        return await _bg_fn(ctx, **{_bg_pydantic_param: _mi})
                    return await _bg_fn(ctx, **_bg_input)

                _bg_task_id = await ctx.background_task(
                    _bg_coro(),
                    long_running=bool(getattr(_func_def, "long_running", False)),
                    name=current_tu.name,
                )
                result = ActionResult.success(
                    summary=(
                        f"Started '{current_tu.name}' in background — "
                        "the result will be sent to chat when it finishes."
                    ),
                    data={"task_id": _bg_task_id, "background": True},
                )
            elif _func_def._pydantic_model and _func_def._pydantic_param:
                _model_instance = _func_def._pydantic_model(**(current_tu.input or {}))
                result = await _func_def.func(ctx, **{_func_def._pydantic_param: _model_instance})
            else:
                result = await _func_def.func(ctx, **current_tu.input)

            # === SUCCESS path ===
            _is_action_result = isinstance(result, ActionResult)
            if _is_action_result:
                content = json.dumps(result.to_dict(), default=str, ensure_ascii=False)
            else:
                content = json.dumps(result, default=str, ensure_ascii=False)
                if _func_def.event:
                    log.warning(
                        f"ChatExtension {chat_ext.tool_name}: function '{current_tu.name}' "
                        f"has event='{_func_def.event}' but returned dict, not ActionResult"
                    )
            content = trim_tool_result(
                content, cfg["max_result_tokens"],
                cfg["list_truncate_items"], cfg["string_truncate_chars"],
            )

            if _is_action_result:
                success = result.status == "success"
            else:
                success = True
                if isinstance(result, dict):
                    if result.get("RESULT") == "ERROR" or result.get("error"):
                        success = False
                    elif "success" in result:
                        success = bool(result["success"])

            chat_ext._functions_called.append({
                "name": current_tu.name, "params": current_tu.input,
                "action_type": action_type, "success": success,
                "intercepted": False,
                "event": _func_def.event if _is_action_result else "",
                "result": result if _is_action_result else None,
            })
            _emit_retry_outcome(
                tool=current_tu.name, ext=_ext_name,
                outcome=("no_retry" if retry_count == 0 else "success"),
                retry_count=retry_count,
            )
            return content

        except TaskCancelled:
            raise

        except PydanticValidationError as e:
            if not _retry_eligible or retry_count >= _RETRY_BUDGET:
                # Exhausted OR not eligible for retry — existing failure handling.
                content = _validation_missing_field_response(
                    e=e, chat_ext=chat_ext, tu=current_tu,
                    action_type=action_type, cfg=cfg,
                )
                if _retry_eligible:
                    _emit_retry_outcome(
                        tool=current_tu.name, ext=_ext_name,
                        outcome="exhausted", retry_count=retry_count,
                    )
                return content

            # Retry path: re-prompt LLM with structured prose feedback.
            prose = format_pydantic_for_llm(e)
            log.info(
                f"chat_handler validation_retry tool={current_tu.name} "
                f"retry_count={retry_count + 1}/{_RETRY_BUDGET}"
            )

            tmp_messages = list(retry_ctx["messages"]) + [
                {"role": "assistant", "content": [current_tu]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": current_tu.id, "content": prose}
                ]},
            ]
            retry_resp = await retry_ctx["client"].create_message(
                max_tokens=retry_ctx["_tool_use_mt"],
                system=retry_ctx["_system"],
                messages=tmp_messages,
                tools=retry_ctx["_tools_for_llm"],
                cfg=retry_ctx["_exec_cfg"],
                **retry_ctx["_api_kwargs"],
            )
            # Mirror the main loop's usage callback for retry LLM calls
            # (handler.py:411-426). Without this, retry token cost is silently
            # dropped from billing/observability.
            _usage_cb = getattr(ctx, "_llm_usage_callback", None)
            if _usage_cb and hasattr(retry_resp, "usage") and retry_resp.usage is not None:
                try:
                    from imperal_sdk.runtime.llm_provider import LLMUsage
                    _exec_cfg = retry_ctx["_exec_cfg"]
                    _uid = str(getattr(ctx.user, "id", "")) if hasattr(ctx, "user") and ctx.user else ""
                    _usage = LLMUsage(
                        provider=_exec_cfg.provider,
                        model=_exec_cfg.model,
                        input_tokens=getattr(retry_resp.usage, "input_tokens", 0) or 0,
                        output_tokens=getattr(retry_resp.usage, "output_tokens", 0) or 0,
                        is_byollm=_exec_cfg.is_byollm,
                        purpose="execution",
                        user_id=_uid,
                    )
                    await _usage_cb(_usage)
                except Exception as _e:
                    log.debug(f"retry usage callback failed: {_e}")  # NEVER raise
            new_tools = [b for b in retry_resp.content if getattr(b, "type", None) == "tool_use"]
            new_tu = next((b for b in new_tools if b.name == current_tu.name), None)
            if new_tu is None:
                # LLM gave up (final text or different tool). Existing failure shape.
                content = _validation_missing_field_response(
                    e=e, chat_ext=chat_ext, tu=current_tu,
                    action_type=action_type, cfg=cfg,
                )
                _emit_retry_outcome(
                    tool=current_tu.name, ext=_ext_name,
                    outcome="llm_gave_up", retry_count=retry_count,
                )
                return content

            # I-AH-1 federal re-check on retry (spec section 8 E15).
            _ret_id_rejection = check_id_shape_fabrication(new_tu.input or {})
            if _ret_id_rejection is not None:
                log.warning(
                    "ChatExtension I-AH-1 reject-on-retry %s field=%s value=%r",
                    new_tu.name, _ret_id_rejection["field"], _ret_id_rejection["value"],
                )
                content = json.dumps({"RESULT": "ERROR", **_ret_id_rejection})
                chat_ext._functions_called.append({
                    "name": new_tu.name, "params": new_tu.input,
                    "action_type": action_type, "success": False,
                    "intercepted": True, "event": "",
                    "result": _ret_id_rejection,
                })
                _emit_retry_outcome(
                    tool=current_tu.name, ext=_ext_name,
                    outcome="fabricated_id_on_retry", retry_count=retry_count + 1,
                )
                return trim_tool_result(
                    content, cfg["max_result_tokens"],
                    cfg["list_truncate_items"], cfg["string_truncate_chars"],
                )

            # Redundant retry detection (byte-identical args).
            if json.dumps(new_tu.input or {}, sort_keys=True) == json.dumps(current_tu.input or {}, sort_keys=True):
                _emit_retry_outcome(
                    tool=current_tu.name, ext=_ext_name,
                    outcome="redundant", retry_count=retry_count + 1,
                )
                log.warning(
                    "chat_handler validation_retry_redundant tool=%s args_unchanged=true retry_count=%d",
                    current_tu.name, retry_count + 1,
                )

            current_tu = new_tu
            retry_count += 1
            continue  # while True

        except Exception as e:
            log.error(f"ChatExtension internal error {current_tu.name}: {e}", exc_info=True)
            content = json.dumps({
                "RESULT": "ERROR",
                "error_code": "INTERNAL",
                "error_class": type(e).__name__,
            })
            chat_ext._functions_called.append({
                "name": current_tu.name, "params": current_tu.input,
                "action_type": action_type, "success": False,
                "intercepted": False, "event": "",
                "result": {"error_code": "INTERNAL", "error_class": type(e).__name__},
            })
            return trim_tool_result(
                content, cfg["max_result_tokens"],
                cfg["list_truncate_items"], cfg["string_truncate_chars"],
            )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
