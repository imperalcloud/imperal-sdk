# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Message handling loop for ChatExtension.

Contains the full LLM tool-use loop extracted from ChatExtension._handle().
All state access goes through the `chat_ext` parameter (the ChatExtension instance).

Federal-Grade Chat Integrity hooks (spec 2026-04-23):

  * P2 Task 20 — structured error_code in ``_execute_function`` + unknown
    sub-function early exit. Raw ``str(e)`` no longer lands in tool_result
    content or ``_functions_called[*].result`` — that was the vector
    ``check_write_arg_bleed`` (Task 21) guards against.

  * P2 Task 27 — ``EMIT_NARRATION_TOOL`` is augmented onto every tool list
    passed to ``client.create_message``. When the LLM emits a tool_use with
    ``name == "emit_narration"``, the loop terminates and the parsed
    ``NarrationEmission`` is attached to the returned ``ChatResult`` (or
    ``None`` on malformed input — best-effort prose still surfaces).

  * P2 Task 32 — round-0 ``tool_choice`` enforcement. When the classifier
    stamps ``ctx.skeleton["_fresh_fetch_required"]`` with a single tool name
    the LLM MUST use, we pass ``tool_choice={"type":"tool","name":X}``.
    Multi-tool fresh-fetch falls back to ``tool_choice={"type":"any"}`` +
    post-round verification log line.
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from imperal_sdk.chat.filters import enforce_os_identity, enforce_response_style, normalize_markdown, trim_tool_result
from imperal_sdk.chat.prompt import inject_language
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.chat.guards import check_guards
from imperal_sdk.chat.narration import EMIT_NARRATION_TOOL, NarrationEmission, parse_narration_emission
from imperal_sdk.chat.narration_guard import augment_system_with_narration_rule

if TYPE_CHECKING:
    from imperal_sdk.chat.extension import ChatExtension
    from imperal_sdk.context import Context as _Context

log = logging.getLogger(__name__)


class TaskCancelled(Exception):
    """Raised by ctx.progress() when user cancels a task."""
    pass


# ---------------------------------------------------------------------------
# Config resolution helpers
# ---------------------------------------------------------------------------

def _cfg_get(ctx, key: str, default=None):
    """Safe config lookup."""
    if hasattr(ctx, 'config') and ctx.config:
        val = ctx.config.get(key)
        if val is not None:
            return val
    return default


def _resolve_config(ctx) -> dict:
    """Resolve all context-window and limit configs into a flat dict."""
    _user_attrs = (
        ctx.user.attributes
        if hasattr(ctx, 'user') and ctx.user and hasattr(ctx.user, 'attributes')
        else {}
    )
    return {
        "max_result_tokens": int(_cfg_get(ctx, "context.max_result_tokens") or _cfg_get(ctx, "context_defaults.default_max_result_tokens") or 3000),
        "list_truncate_items": int(_cfg_get(ctx, "context_defaults.list_truncate_items") or 5),
        "string_truncate_chars": int(_cfg_get(ctx, "context_defaults.string_truncate_chars") or 500),
        "context_window": int(_user_attrs.get("context_window") or _cfg_get(ctx, "context_defaults.default_context_window") or 20),
        "keep_recent": int(_cfg_get(ctx, "context.keep_recent_verbatim") or _cfg_get(ctx, "context_defaults.default_keep_recent") or 6),
        "quality_ceiling": int(_cfg_get(ctx, "context_defaults.quality_ceiling_tokens") or 50000),
    }


# ---------------------------------------------------------------------------
# Factual response builder (post-write-action summary)
# ---------------------------------------------------------------------------

async def _build_factual_response(chat_ext: ChatExtension, ctx, client) -> str:
    """Build a factual LLM summary after successful write actions."""
    _factual_parts = []
    for fc in chat_ext._functions_called:
        if fc.get("intercepted"):
            continue
        _fname = fc.get("name", "action")
        _result = fc.get("result")
        if fc.get("success"):
            _summary = ""
            if _result and hasattr(_result, "summary") and _result.summary:
                _summary = str(_result.summary)[:500]
            elif _result and hasattr(_result, "data") and _result.data:
                _data = _result.data
                _summary = str(_data)[:500] if isinstance(_data, dict) else f"{len(_data)} items" if isinstance(_data, list) else ""
            _factual_parts.append(f"{_fname}: SUCCESS" + (f" — {_summary}" if _summary else ""))
        else:
            _err = str(_result.error)[:200] if _result and hasattr(_result, "error") and _result.error else ""
            _factual_parts.append(f"{_fname}: FAILED" + (f" — {_err}" if _err else ""))

    _factual_summary = "\n".join(_factual_parts) if _factual_parts else "Action completed."
    _response_tokens = int(_cfg_get(ctx, "user_settings.max_response_tokens") or _cfg_get(ctx, "max_response_tokens", 1024) or 1024)

    try:
        _lang_hint = ""
        _ulang = getattr(ctx, "_user_language_name", "")
        if _ulang and _ulang.lower() != "english":
            _lang_hint = f" Respond in {_ulang}."
        _uid = str(getattr(ctx.user, "id", "")) if hasattr(ctx, "user") and ctx.user else ""
        _factual_system = (
            f"Format the action results into a detailed, natural response.{_lang_hint} "
            "Describe what each function did with specifics from the results. Be thorough. No emojis."
        )
        # I-NARRATION-STRICT-1: every narration LLM call must carry the
        # strict anti-fabrication postamble. Non-regex, language-agnostic.
        _factual_system = augment_system_with_narration_rule(
            _factual_system, chat_ext._functions_called
        )
        final_resp = await client.create_message(
            max_tokens=_response_tokens,
            system=_factual_system,
            messages=[{"role": "user", "content": f"Action results:\n{_factual_summary}"}],
            purpose="execution", user_id=_uid,
        )
        return next((b.text for b in final_resp.content if hasattr(b, "text")), _factual_summary)
    except Exception:
        return _factual_summary


# ---------------------------------------------------------------------------
# Function execution  (P2 Task 20 — structured error_code surfaces)
# ---------------------------------------------------------------------------

async def _execute_function(chat_ext: ChatExtension, ctx, tu, action_type: str, cfg: dict) -> str:
    """Execute a single function call and return the tool result content string.

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
    try:
        if _func_def._pydantic_model and _func_def._pydantic_param:
            _model_instance = _func_def._pydantic_model(**(tu.input or {}))
            result = await _func_def.func(ctx, **{_func_def._pydantic_param: _model_instance})
        else:
            result = await _func_def.func(ctx, **tu.input)

        _is_action_result = isinstance(result, ActionResult)
        if _is_action_result:
            content = json.dumps(result.to_dict(), default=str, ensure_ascii=False)
        else:
            content = json.dumps(result, default=str, ensure_ascii=False)
            if _func_def.event:
                log.warning(f"ChatExtension {chat_ext.tool_name}: function '{tu.name}' has event='{_func_def.event}' but returned dict, not ActionResult")
        content = trim_tool_result(content, cfg["max_result_tokens"], cfg["list_truncate_items"], cfg["string_truncate_chars"])

        # Determine success
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
            "name": tu.name, "params": tu.input, "action_type": action_type,
            "success": success, "intercepted": False,
            "event": _func_def.event if _is_action_result else "",
            "result": result if _is_action_result else None,
        })
        return content

    except TaskCancelled:
        raise

    except PydanticValidationError as e:
        # Arg-validation failure on the auto-detected Pydantic model. Surface
        # missing fields explicitly so the LLM can self-correct without
        # having to parse a freeform string. This is also the error surface
        # the write-arg-bleed guard (Task 21) reads on subsequent calls.
        missing = []
        for err in e.errors():
            if err.get("type") == "missing":
                loc = err.get("loc") or ()
                if loc:
                    missing.append(loc[0])
        log.error(f"ChatExtension validation error {tu.name}: missing={missing}")
        content = json.dumps({
            "RESULT": "ERROR",
            "error_code": "VALIDATION_MISSING_FIELD",
            "missing_fields": missing,
        })
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input, "action_type": action_type,
            "success": False, "intercepted": False, "event": "",
            "result": {"error_code": "VALIDATION_MISSING_FIELD", "missing_fields": missing},
        })
        return trim_tool_result(content, cfg["max_result_tokens"], cfg["list_truncate_items"], cfg["string_truncate_chars"])

    except Exception as e:
        # Generic internal failure. error_class is the exception type name
        # (safe to expose) but str(e) is NOT included — it has leaked PII,
        # paths, and credentials historically.
        log.error(f"ChatExtension internal error {tu.name}: {e}", exc_info=True)
        content = json.dumps({
            "RESULT": "ERROR",
            "error_code": "INTERNAL",
            "error_class": type(e).__name__,
        })
        chat_ext._functions_called.append({
            "name": tu.name, "params": tu.input, "action_type": action_type,
            "success": False, "intercepted": False, "event": "",
            "result": {"error_code": "INTERNAL", "error_class": type(e).__name__},
        })
        return trim_tool_result(content, cfg["max_result_tokens"], cfg["list_truncate_items"], cfg["string_truncate_chars"])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def handle_message(chat_ext: ChatExtension, ctx: _Context, message: str = "", **kwargs) -> dict:
    """Full LLM tool-use loop — extracted from ChatExtension._handle()."""
    chat_ext._functions_called = []
    cfg = _resolve_config(ctx)
    _max_tool_rounds = int(_cfg_get(ctx, "user_settings.max_tool_rounds") or _cfg_get(ctx, "context.max_tool_rounds") or chat_ext.max_rounds)

    from imperal_sdk.runtime.llm_provider import get_llm_provider
    client = get_llm_provider()
    tools = chat_ext._build_tool_schemas()
    if not tools:
        return chat_ext._make_chat_result(response="No functions registered")

    # P2 Task 27 — augment the extension's tools with EMIT_NARRATION_TOOL.
    # Shared ref (not a copy) so provider adapters can identity-compare.
    _tools_for_llm = list(tools) + [EMIT_NARRATION_TOOL]

    system = chat_ext._build_system_prompt(ctx)
    _sys_tokens_est = len(system) // 3
    _effective_window = cfg["context_window"]
    if _sys_tokens_est > 2000 and cfg["context_window"] > cfg["keep_recent"] + 4:
        _effective_window = max(cfg["context_window"] - 4, cfg["keep_recent"])
        log.info(f"ChatExtension {chat_ext.tool_name}: large system prompt ({_sys_tokens_est} est tokens), reducing window {cfg['context_window']} -> {_effective_window}")

    messages = chat_ext._build_messages(
        ctx.history if hasattr(ctx, "history") else [], message,
        context_window=_effective_window, keep_recent=cfg["keep_recent"],
    )
    inject_language(messages, getattr(ctx, '_user_language', None), getattr(ctx, '_user_language_name', None))

    kav_injection = getattr(ctx, "_kav_injection", None) or kwargs.get("_kav_injection")
    if kav_injection:
        messages.append({"role": "user", "content": kav_injection})

    confirmation_required = getattr(ctx, "_confirmation_required", False) or kwargs.get("_confirmation_required", False)

    # ctx.progress() injection
    _progress_fn = getattr(ctx, '_progress_callback', None)
    _task_id = getattr(ctx, '_task_id', None)

    async def _ctx_progress(percent: float, msg: str = ""):
        if _progress_fn:
            cancelled = await _progress_fn(percent, msg)
            if cancelled:
                raise TaskCancelled(f"Task {_task_id} cancelled by user")

    if not hasattr(ctx, 'progress'):
        ctx.progress = _ctx_progress

    _chain_mode = getattr(ctx, "_chain_mode", False)

    # P2 Task 32 — classifier fresh-fetch hint. When the classifier knows
    # the user's turn requires a live read (e.g. "new mail?" demands an
    # inbox fetch because skeleton snapshot is stale), it stamps
    # ``ctx.skeleton["_fresh_fetch_required"] = [tool_name, ...]``. We
    # honour the hint on round 0 only.
    _required_fresh: list[str] = []
    if isinstance(getattr(ctx, "skeleton", None), dict):
        _required_fresh = list(ctx.skeleton.get("_fresh_fetch_required", []) or [])

    try:
        for _round in range(_max_tool_rounds):
            _api_kwargs: dict = {}

            # Pre-existing rule: first round or chain mode → force tool use.
            if (_chain_mode or (_round == 0 and tools)) and _round == 0:
                _api_kwargs["tool_choice"] = {"type": "any"}
                log.info(f"ChatExtension {chat_ext.tool_name}: forcing tool_choice=any (chain={_chain_mode})")

            # P2 Task 32 — fresh-fetch override of tool_choice on round 0.
            if _required_fresh and _round == 0:
                if len(_required_fresh) == 1 and _required_fresh[0] in chat_ext._functions:
                    _api_kwargs["tool_choice"] = {"type": "tool", "name": _required_fresh[0]}
                    log.info(
                        f"ChatExtension {chat_ext.tool_name}: fresh-fetch enforcement "
                        f"tool_choice={_required_fresh[0]}"
                    )
                else:
                    # Multi-required: Anthropic tool_choice cannot express OR
                    # over tool names. Fall back to "any" + post-round verify.
                    log.info(
                        f"ChatExtension {chat_ext.tool_name}: fresh-fetch multi-required "
                        f"fallback tool_choice=any required={_required_fresh}"
                    )
                    _api_kwargs["tool_choice"] = {"type": "any"}

            # Observability
            _msg_tokens_est = sum(len(m["content"]) if isinstance(m["content"], str) else sum(len(str(x)) for x in m["content"]) if isinstance(m["content"], list) else 0 for m in messages) // 3
            _total_est = _sys_tokens_est + _msg_tokens_est
            if _total_est > cfg["quality_ceiling"]:
                log.warning(f"Context OVER ceiling: {_total_est}/{cfg['quality_ceiling']} system={_sys_tokens_est} msgs={_msg_tokens_est} round={_round} ext={chat_ext.tool_name}")
            elif _round == 0:
                log.info(f"Context budget: system={_sys_tokens_est} msgs={_msg_tokens_est} total={_total_est} window={_effective_window} ext={chat_ext.tool_name}")

            _uid = str(getattr(ctx.user, "id", "")) if hasattr(ctx, "user") and ctx.user else ""
            # I-NARRATION-STRICT-1: augment system prompt with anti-fabrication
            # postamble carrying the current _functions_called snapshot (belt-
            # and-suspenders alongside EMIT_NARRATION_TOOL per spec §3.9).
            # Language-agnostic. Coexists with P2 emit_narration terminal tool.
            _system_for_round = augment_system_with_narration_rule(
                system, chat_ext._functions_called
            )
            resp = await client.create_message(
                max_tokens=2048, system=_system_for_round, messages=messages,
                tools=_tools_for_llm,
                purpose="execution", user_id=_uid, **_api_kwargs,
            )

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                text = next((b.text for b in resp.content if hasattr(b, "text")), "Done.")
                text = enforce_os_identity(text)
                text = enforce_response_style(text)
                text = normalize_markdown(text)
                return chat_ext._make_chat_result(response=text, handled=bool(chat_ext._functions_called))

            # P2 Task 27 — emit_narration is a terminal tool. If present in
            # the batch, exit immediately with the parsed emission attached.
            for tu in tool_uses:
                if tu.name == "emit_narration":
                    emission: NarrationEmission | None = None
                    _tu_input = tu.input if isinstance(tu.input, dict) else {}
                    try:
                        emission = parse_narration_emission(_tu_input)
                    except Exception as e:
                        log.error(f"ChatExtension {chat_ext.tool_name}: emit_narration parse error: {e}")
                        emission = None
                    text = _tu_input.get("prose", "") if isinstance(_tu_input, dict) else ""
                    text = enforce_os_identity(text)
                    text = enforce_response_style(text)
                    text = normalize_markdown(text)
                    return chat_ext._make_chat_result(
                        response=text,
                        handled=bool(chat_ext._functions_called),
                        narration_emission=emission.model_dump() if emission is not None else None,
                    )

            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for tu in tool_uses:
                action_type = chat_ext._get_action_type(tu.name)
                log.info(f"ChatExtension {chat_ext.tool_name} (round {_round+1}): {tu.name}({tu.input}) [action_type={action_type}]")

                guard_content = check_guards(chat_ext, ctx, tu, action_type, confirmation_required)
                if guard_content is not None:
                    tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": guard_content})
                    continue

                content = await _execute_function(chat_ext, ctx, tu, action_type, cfg)
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})

            if any(fc["intercepted"] for fc in chat_ext._functions_called):
                return chat_ext._make_chat_result(response="Action requires confirmation.", intercepted=True, message_type="confirmation")

            messages.append({"role": "user", "content": tool_results})

            # P2 Task 32 — fresh-fetch verification on round 0. The hint is
            # best-effort: we log a violation but don't hard-fail — the
            # kernel narration verifier (Task 28) handles consistency.
            if _round == 0 and _required_fresh:
                _recent = chat_ext._functions_called[-len(tool_uses):] if tool_uses else []
                called_names = {fc["name"] for fc in _recent}
                missing_fresh = [r for r in _required_fresh if r not in called_names]
                if missing_fresh:
                    log.warning(
                        f"ChatExtension {chat_ext.tool_name}: fresh-fetch violation "
                        f"round 0 missed={missing_fresh}"
                    )

            if _round >= 1:
                has_successful_write = any(fc["action_type"] in ("write", "destructive") and fc["success"] for fc in chat_ext._functions_called if not fc["intercepted"])
                if has_successful_write:
                    log.info(f"ChatExtension {chat_ext.tool_name}: write action succeeded on round {_round+1}, building factual response")
                    text = await _build_factual_response(chat_ext, ctx, client)
                    text = enforce_os_identity(text)
                    text = enforce_response_style(text)
                    text = normalize_markdown(text)
                    return chat_ext._make_chat_result(response=text, handled=True)

        return chat_ext._make_chat_result(response="Request required too many steps. Please simplify.", handled=bool(chat_ext._functions_called))

    except TaskCancelled:
        chat_ext._functions_called.append({
            "name": "__cancelled__", "params": {}, "action_type": "read",
            "success": False, "intercepted": False, "error": "Task cancelled by user",
            "event": "", "result": None,
        })
        return chat_ext._make_chat_result(response="Task cancelled.", task_cancelled=True, handled=bool(chat_ext._functions_called))
    except Exception as e:
        log.error(f"ChatExtension error: {e}")
        # Preserve partial results: if earlier rounds invoked tools
        # successfully (e.g. inbox, search) and only the final narration
        # round died on Connection error / model crash, don't throw away
        # the accumulated data — surface it to the user instead of a
        # generic "No extension handled" refusal. Kernel will read
        # handled=True + _functions_called and the user sees what we
        # actually got.
        if chat_ext._functions_called:
            try:
                _ok_calls = [fc for fc in chat_ext._functions_called
                             if isinstance(fc, dict) and fc.get("success") and not fc.get("intercepted")]
            except Exception:
                _ok_calls = []
            if _ok_calls:
                _names = ", ".join(sorted({fc.get("name","?") for fc in _ok_calls}))
                _partial = (
                    f"I ran {_names} and collected your data, but the model hit "
                    f"a Connection issue while formatting the final reply "
                    f"(likely a local-LLM hiccup). Showing the raw action log; "
                    f"retry in a moment if you want the full narrative."
                )
                return chat_ext._make_chat_result(
                    response=_partial,
                    handled=True,
                )
        return chat_ext._make_chat_result(response=f"Error: {e}")
