# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""ChatExtension — single entry point with LLM routing for extensions."""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from imperal_sdk.context import Context as _Context

try:
    from imperal_sdk.runtime.executor import _check_target_scope
except ImportError:
    import logging as _log_tsc
    _log_tsc.getLogger(__name__).error("CRITICAL: _check_target_scope import failed — all cross-user actions will be BLOCKED")
    def _check_target_scope(**kwargs):
        return {"allowed": False, "cross_user": True, "error": "target_scope_unavailable"}
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.chat.filters import enforce_os_identity, enforce_response_style, trim_tool_result
from imperal_sdk.chat.prompt import build_system_prompt, build_messages, inject_language, ICNLI_INTEGRITY_RULES

log = logging.getLogger(__name__)


class TaskCancelled(Exception):
    """Raised by ctx.progress() when user cancels a task."""
    pass


# Words that indicate write/destructive actions — used for backwards-compatible
# action_type detection when no explicit action_type is set on a function.
_ACTION_WORDS = ("send", "create", "delete", "update", "archive", "reply", "forward", "remove", "move", "trash")

@dataclass
class FunctionDef:
    name: str
    func: Callable
    description: str
    params: dict = field(default_factory=dict)
    action_type: str = "read"  # "read", "write", or "destructive"
    event: str = ""  # event name for ActionResult publishing (e.g. "mail.sent")
    event_schema: type | None = None  # Pydantic BaseModel for typed event data
    _pydantic_model: type | None = None  # auto-detected Pydantic BaseModel class
    _pydantic_param: str = ""  # parameter name that receives the model instance

class ChatExtension:
    def __init__(self, ext, tool_name: str, description: str, system_prompt: str = "",
                 model: str = "claude-haiku-4-5-20251001", max_rounds: int = 10):
        self.ext = ext
        self.tool_name = tool_name
        self.description = description
        self.system_prompt = system_prompt
        self.model = model
        self.max_rounds = max_rounds
        self._functions: dict[str, FunctionDef] = {}
        _self = self
        ext._chat_extensions = getattr(ext, "_chat_extensions", {})
        ext._chat_extensions[tool_name] = self
        @ext.tool(tool_name, scopes=["*"], description=description)
        async def _entry_point(ctx, message="", **kwargs):
            return await _self._handle(ctx, message, **kwargs)

    def function(self, name: str, description: str, params: dict | None = None,
                 action_type: str = "read", event: str = "",
                 event_schema: type | None = None):
        """Register a chat function.

        Args:
            name: Function name (used in tool_use calls).
            description: What this function does (shown to LLM).
            params: Parameter definitions dict.
            action_type: "read", "write", or "destructive". Default "read".
                         Used by KAV for action verification and 2-step confirmation.
            event: Event name for ActionResult publishing (e.g. "mail.sent").
            event_schema: Optional Pydantic BaseModel class for typed event data validation.
        """
        def decorator(func: Callable) -> Callable:
            # Auto-detect Pydantic BaseModel params
            resolved_params = params
            _detected_model = None
            _detected_param = ""
            if resolved_params is None:
                import inspect
                sig = inspect.signature(func)
                for pname, param in sig.parameters.items():
                    if pname in ("ctx", "self"):
                        continue
                    ann = param.annotation
                    if ann != inspect.Parameter.empty:
                        # PEP 563: from __future__ import annotations → strings
                        if isinstance(ann, str):
                            try:
                                ann = eval(ann, func.__globals__)
                            except Exception:
                                continue
                        try:
                            from pydantic import BaseModel
                            if isinstance(ann, type) and issubclass(ann, BaseModel):
                                schema = ann.model_json_schema()
                                resolved_params = {}
                                for field_name, field_info in schema.get("properties", {}).items():
                                    resolved_params[field_name] = {
                                        "type": field_info.get("type", "string"),
                                        "description": field_info.get("description", field_info.get("title", "")),
                                    }
                                    if field_name not in schema.get("required", []):
                                        resolved_params[field_name]["default"] = field_info.get("default")
                                _detected_model = ann
                                _detected_param = pname
                                break
                        except (TypeError, ImportError):
                            pass
            if resolved_params is None:
                resolved_params = {}

            self._functions[name] = FunctionDef(
                name=name, func=func, description=description,
                params=resolved_params, action_type=action_type, event=event,
                event_schema=event_schema,
                _pydantic_model=_detected_model, _pydantic_param=_detected_param,
            )
            return func
        return decorator

    @property
    def functions(self) -> dict[str, FunctionDef]:
        return self._functions

    def _make_chat_result(self, response: str, handled: bool = False,
                          message_type: str = "text", intercepted: bool = False,
                          task_cancelled: bool = False, action_meta: dict = None) -> dict:
        """Build return dict using ChatResult for typed construction."""
        from imperal_sdk.types.chat_result import ChatResult, FunctionCall as FC

        fcs = []
        for fc_dict in self._functions_called:
            fcs.append(FC(
                name=fc_dict.get("name", ""),
                params=fc_dict.get("params", {}),
                action_type=fc_dict.get("action_type", "read"),
                success=fc_dict.get("success", False),
                intercepted=fc_dict.get("intercepted", False),
                event=fc_dict.get("event", ""),
            ))

        cr = ChatResult(
            response=response,
            handled=handled,
            functions_called=fcs,
            had_successful_action=any(
                fc.success and fc.action_type in ("write", "destructive")
                for fc in fcs
            ),
            message_type=message_type,
            action_meta=action_meta or {},
            intercepted=intercepted,
            task_cancelled=task_cancelled,
        )
        return cr.to_dict()

    def _get_action_type(self, func_name: str) -> str:
        """Return the action_type for a function. Falls back to name-based detection."""
        if func_name in self._functions:
            at = self._functions[func_name].action_type
            if at != "read":
                return at
            # Backwards compat: if still "read" (default), check name for write words
            if any(w in func_name.lower() for w in _ACTION_WORDS):
                return "write"
            return "read"
        # Unknown function — try name-based detection
        if any(w in func_name.lower() for w in _ACTION_WORDS):
            return "write"
        return "read"

    def _build_tool_schemas(self) -> list[dict]:
        tools = []
        for fn in self._functions.values():
            properties = {}
            required = []
            for pname, pdef in fn.params.items():
                prop = {"type": pdef.get("type", "string")}
                if "description" in pdef: prop["description"] = pdef["description"]
                if "enum" in pdef: prop["enum"] = pdef["enum"]
                properties[pname] = prop
                if "default" not in pdef: required.append(pname)
            tools.append({"name": fn.name, "description": fn.description,
                         "input_schema": {"type": "object", "properties": properties, "required": required}})
        return tools

    def _build_system_prompt(self, ctx) -> str:
        return build_system_prompt(self.system_prompt, ctx, self.tool_name)

    def _build_messages(self, history, message, context_window=20, keep_recent=6):
        return build_messages(history, message, context_window, keep_recent)

    async def _handle(self, ctx: _Context, message: str = "", **kwargs) -> dict:
        self._functions_called = []

        # ── Context Window config resolution ──────────────────────
        _max_result_tokens = int(
            (ctx.config.get("context.max_result_tokens") if hasattr(ctx, 'config') and ctx.config else None)
            or (ctx.config.get("context_defaults.default_max_result_tokens") if hasattr(ctx, 'config') and ctx.config else None)
            or 3000
        )
        _list_truncate_items = int(
            (ctx.config.get("context_defaults.list_truncate_items") if hasattr(ctx, 'config') and ctx.config else None)
            or 5
        )
        _string_truncate_chars = int(
            (ctx.config.get("context_defaults.string_truncate_chars") if hasattr(ctx, 'config') and ctx.config else None)
            or 500
        )

        # History window: user attribute > platform default > 20
        _user_attrs = ctx.user.attributes if hasattr(ctx, 'user') and ctx.user and hasattr(ctx.user, 'attributes') else {}
        _context_window = int(
            _user_attrs.get("context_window")
            or (ctx.config.get("context_defaults.default_context_window") if hasattr(ctx, 'config') and ctx.config else None)
            or 20
        )
        _keep_recent = int(
            (ctx.config.get("context.keep_recent_verbatim") if hasattr(ctx, 'config') and ctx.config else None)
            or (ctx.config.get("context_defaults.default_keep_recent") if hasattr(ctx, 'config') and ctx.config else None)
            or 6
        )

        # Per-extension tool rounds: user_settings > context > constructor default > 10
        _max_tool_rounds = int(
            (ctx.config.get("user_settings.max_tool_rounds") if hasattr(ctx, 'config') and ctx.config else None)
            or (ctx.config.get("context.max_tool_rounds") if hasattr(ctx, 'config') and ctx.config else None)
            or self.max_rounds
        )

        # Observability: quality ceiling for warning threshold
        _quality_ceiling = int(
            (ctx.config.get("context_defaults.quality_ceiling_tokens") if hasattr(ctx, 'config') and ctx.config else None)
            or 50000
        )

        from imperal_sdk.runtime.llm_provider import get_llm_provider
        client = get_llm_provider()
        tools = self._build_tool_schemas()
        if not tools: return self._make_chat_result(response="No functions registered")
        system = self._build_system_prompt(ctx)
        # System prompt awareness: reduce window if prompt is very large
        _sys_tokens_est = len(system) // 3
        _effective_window = _context_window
        if _sys_tokens_est > 2000 and _context_window > _keep_recent + 4:
            _effective_window = max(_context_window - 4, _keep_recent)
            log.info(f"ChatExtension {self.tool_name}: large system prompt ({_sys_tokens_est} est tokens), "
                     f"reducing window {_context_window} -> {_effective_window}")

        messages = self._build_messages(
            ctx.history if hasattr(ctx, "history") else [],
            message,
            context_window=_effective_window,
            keep_recent=_keep_recent,
        )

        # KERNEL LANGUAGE ENFORCEMENT (model-agnostic, works with Sonnet/Opus/GPT/any)
        # Inject language rule into the LAST user message — models follow recent instructions best.
        # System prompt rule alone is insufficient for some models (Sonnet ignores it).
        inject_language(messages, getattr(ctx, '_user_language', None), getattr(ctx, '_user_language_name', None))

        # KAV injection: kernel can inject a retry message telling LLM to actually call the function
        kav_injection = getattr(ctx, "_kav_injection", None) or kwargs.get("_kav_injection")
        if kav_injection:
            messages.append({"role": "user", "content": kav_injection})

        # Check if confirmation is required (2-step confirmation mode)
        confirmation_required = getattr(ctx, "_confirmation_required", False) or kwargs.get("_confirmation_required", False)

        # ── ctx.progress() injection ──────────────────────────────
        _progress_fn = getattr(ctx, '_progress_callback', None)
        _task_id = getattr(ctx, '_task_id', None)

        async def _ctx_progress(percent: float, message: str = ""):
            if _progress_fn:
                cancelled = await _progress_fn(percent, message)
                if cancelled:
                    raise TaskCancelled(f"Task {_task_id} cancelled by user")

        if not hasattr(ctx, 'progress'):
            ctx.progress = _ctx_progress

        # Chain mode: kernel guarantees each step calls functions (tool_choice=any on round 1)
        _chain_mode = getattr(ctx, "_chain_mode", False)

        try:
            for _round in range(_max_tool_rounds):
                _api_kwargs = {}
                # tool_choice="any" on round 1 when tools available.
                # Hub KERNEL GATE guarantees only actionable messages reach extensions.
                # If we're here, the message NEEDS a function call.
                _force_fn = _chain_mode or (_round == 0 and tools)
                if _force_fn and _round == 0:
                    _api_kwargs["tool_choice"] = {"type": "any"}
                    log.info(f"ChatExtension {self.tool_name}: forcing tool_choice=any (chain={_chain_mode})")
                # Guard 6: Observability — log context composition
                _msg_tokens_est = sum(
                    len(m["content"]) if isinstance(m["content"], str)
                    else sum(len(str(x)) for x in m["content"]) if isinstance(m["content"], list)
                    else 0
                    for m in messages
                ) // 3
                _total_est = _sys_tokens_est + _msg_tokens_est
                if _total_est > _quality_ceiling:
                    log.warning(
                        f"Context OVER ceiling: {_total_est}/{_quality_ceiling} "
                        f"system={_sys_tokens_est} msgs={_msg_tokens_est} "
                        f"round={_round} ext={self.tool_name}"
                    )
                elif _round == 0:
                    log.info(
                        f"Context budget: system={_sys_tokens_est} msgs={_msg_tokens_est} "
                        f"total={_total_est} window={_effective_window} ext={self.tool_name}"
                    )

                _uid = str(getattr(ctx.user, "id", "")) if hasattr(ctx, "user") and ctx.user else ""
                resp = await client.create_message(max_tokens=2048, system=system, messages=messages, tools=tools, purpose="execution", user_id=_uid, **_api_kwargs)
                tool_uses = [b for b in resp.content if b.type == "tool_use"]
                if not tool_uses:
                    text = next((b.text for b in resp.content if hasattr(b, "text")), "Done.")
                    text = enforce_os_identity(text)
                    text = enforce_response_style(text)
                    return self._make_chat_result(response=text, handled=bool(self._functions_called))
                messages.append({"role": "assistant", "content": resp.content})
                tool_results = []
                for tu in tool_uses:
                    action_type = self._get_action_type(tu.name)
                    log.info(f"ChatExtension {self.tool_name} (round {_round+1}): {tu.name}({tu.input}) [action_type={action_type}]")

                    # KERNEL GUARD: if intent=read but LLM tries write/destructive → block
                    # Prevents "are you sure?" being interpreted as delete command
                    # Special intents that bypass the guard:
                    #   "chain"      — chain mode: function's @chat.function(action_type=...) is authoritative
                    #   "automation" — automation mode: system-initiated, all actions allowed
                    _ctx_intent = getattr(ctx, "_intent_type", None) or "read"
                    if _ctx_intent in ("chain", "automation"):
                        pass  # Bypass: function's own action_type is the source of truth
                    elif _ctx_intent == "read" and action_type in ("write", "destructive"):
                        log.warning(f"ChatExtension {self.tool_name}: BLOCKED {tu.name} (action={action_type}) — intent is read")
                        self._functions_called.append({
                            "name": tu.name, "params": tu.input,
                            "action_type": action_type, "success": False, "intercepted": False,
                            "event": "", "result": None,
                        })
                        content = json.dumps({
                            "RESULT": "BLOCKED",
                            "error": f"Cannot execute {action_type} action '{tu.name}' — the user's request was classified as read-only. Call a read/list function instead.",
                        })
                        tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
                        continue

                    # -- TARGET SCOPE GUARD (kernel-only, skipped in SDK-only mode) ----------------------------------------
                    # Kernel-level: block cross-user actions without proper scopes
                    _caller_id = str(getattr(ctx.user, 'id', '')) if hasattr(ctx, 'user') and ctx.user else ''
                    _caller_email = str(getattr(ctx.user, 'email', '')) if hasattr(ctx, 'user') and ctx.user else ''
                    _caller_scopes = getattr(ctx.user, 'scopes', ['*']) if hasattr(ctx, 'user') and ctx.user else ['*']
                    # Connected emails from skeleton (multi-account support)
                    _connected_emails = []
                    if hasattr(ctx, 'skeleton_data') and ctx.skeleton_data:
                        _accts = ctx.skeleton_data.get('email_accounts', [])
                        if isinstance(_accts, list):
                            _connected_emails = [a.get('email', '') for a in _accts if a.get('email')]

                    _tsg = _check_target_scope(  # type: ignore
                        tool_use_params=tu.input,
                        caller_id=_caller_id,
                        caller_email=_caller_email,
                        caller_scopes=_caller_scopes,
                        intent_type=action_type,
                        connected_emails=_connected_emails,
                    )

                    if not _tsg["allowed"]:
                        log.warning(f"ChatExtension {self.tool_name}: TARGET_SCOPE BLOCKED {tu.name} target={_tsg['target_user_id']}")
                        self._functions_called.append({
                            "name": tu.name, "params": tu.input,
                            "action_type": action_type, "success": False, "intercepted": False,
                            "event": "", "result": None,
                            "_target_scope": _tsg,
                        })
                        content = json.dumps({
                            "RESULT": "BLOCKED",
                            "error": f"Cross-user action blocked. Required scope: {_tsg['required_scope']}. "
                                     f"You are operating on user '{_tsg['target_user_id']}' which is not the current user.",
                        })
                        tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
                        continue

                    if _tsg.get("force_confirmation") and not confirmation_required:
                        # Destructive cross-user: force 2-Step even if user has not enabled confirmations
                        log.info(f"ChatExtension {self.tool_name}: TARGET_SCOPE forcing confirmation for {tu.name}")
                        self._functions_called.append({
                            "name": tu.name, "params": tu.input,
                            "action_type": action_type, "success": False, "intercepted": True,
                            "event": "", "result": None,
                            "_target_scope": _tsg,
                        })
                        content = json.dumps({
                            "RESULT": "INTERCEPTED",
                            "message": f"This destructive action targets another user ({_tsg['target_user_id']}). Confirmation required.",
                            "function": tu.name,
                            "params": tu.input,
                            "action_type": action_type,
                        })
                        tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
                        continue

                    # 2-step confirmation: intercept based on EXACT category match
                    # ctx._confirmation_actions = {"destructive": True, "write": False} etc.
                    _should_confirm = False
                    if confirmation_required and action_type in ("write", "destructive"):
                        _conf_acts = getattr(ctx, "_confirmation_actions", {})
                        if isinstance(_conf_acts, dict):
                            _should_confirm = _conf_acts.get(action_type, False) or _conf_acts.get("all", False)
                        else:
                            _should_confirm = action_type in _conf_acts or "all" in _conf_acts
                    if _should_confirm:
                        call_record = {
                            "name": tu.name,
                            "params": tu.input,
                            "action_type": action_type,
                            "success": False,
                            "intercepted": True,
                            "event": "", "result": None,
                        }
                        self._functions_called.append(call_record)
                        content = json.dumps({
                            "RESULT": "INTERCEPTED",
                            "message": "Action requires user confirmation before execution.",
                            "function": tu.name,
                            "params": tu.input,
                            "action_type": action_type,
                        })
                        tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})
                        continue

                    if tu.name in self._functions:
                        _func_def = self._functions[tu.name]
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
                                    log.warning(f"ChatExtension {self.tool_name}: function '{tu.name}' has event='{_func_def.event}' but returned dict, not ActionResult")
                            content = trim_tool_result(content, _max_result_tokens, _list_truncate_items, _string_truncate_chars)
                            # Determine success: ActionResult.status or legacy dict heuristics
                            if _is_action_result:
                                success = result.status == "success"
                            else:
                                success = True
                                if isinstance(result, dict):
                                    if result.get("RESULT") == "ERROR" or result.get("error"):
                                        success = False
                                    elif "success" in result:
                                        success = bool(result["success"])
                            self._functions_called.append({
                                "name": tu.name,
                                "params": tu.input,
                                "action_type": action_type,
                                "success": success,
                                "intercepted": False,
                                "event": _func_def.event if _is_action_result else "",
                                "result": result if _is_action_result else None,
                            })
                        except TaskCancelled:
                            raise  # Re-raise to be caught by outer handler
                        except Exception as e:
                            log.error(f"ChatExtension function error {tu.name}: {e}")
                            content = json.dumps({"RESULT": "ERROR", "error": str(e)})
                            content = trim_tool_result(content, _max_result_tokens, _list_truncate_items, _string_truncate_chars)
                            self._functions_called.append({
                                "name": tu.name,
                                "params": tu.input,
                                "action_type": action_type,
                                "success": False,
                                "intercepted": False,
                                "event": "", "result": None,
                            })
                    else:
                        content = json.dumps({"RESULT": "ERROR", "error": f"Unknown function '{tu.name}'. Available: {list(self._functions.keys())}"})
                        content = trim_tool_result(content, _max_result_tokens, _list_truncate_items, _string_truncate_chars)
                        self._functions_called.append({
                            "name": tu.name,
                            "params": tu.input,
                            "action_type": action_type,
                            "success": False,
                            "intercepted": False,
                            "event": "", "result": None,
                        })
                    tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": content})

                # If any function was intercepted, return immediately for confirmation
                if any(fc["intercepted"] for fc in self._functions_called):
                    return self._make_chat_result(
                        response="Action requires confirmation.",
                        intercepted=True,
                        message_type="confirmation",
                    )

                messages.append({"role": "user", "content": tool_results})

                # Action completion: stop after write action ONLY on round 2+
                # Round 1 always continues — allows multi-step (send + forward) in round 2
                # Round 2+: if write action succeeded, stop (prevents infinite loops)
                if _round >= 1:
                    has_successful_write = any(
                        fc["action_type"] in ("write", "destructive") and fc["success"]
                        for fc in self._functions_called
                        if not fc["intercepted"]
                    )
                    if has_successful_write:
                        log.info(f"ChatExtension {self.tool_name}: write action succeeded on round {_round+1}, building factual response")
                        # KERNEL GUARANTEE: build factual response from function results + data.
                        # Includes ActionResult.summary for rich context.
                        _factual_parts = []
                        for fc in self._functions_called:
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
                                    if isinstance(_data, dict):
                                        _summary = str(_data)[:500]
                                    elif isinstance(_data, list):
                                        _summary = f"{len(_data)} items"
                                if _summary:
                                    _factual_parts.append(f"{_fname}: SUCCESS — {_summary}")
                                else:
                                    _factual_parts.append(f"{_fname}: SUCCESS")
                            else:
                                _err = ""
                                if _result and hasattr(_result, "error") and _result.error:
                                    _err = str(_result.error)[:200]
                                _factual_parts.append(f"{_fname}: FAILED" + (f" — {_err}" if _err else ""))
                        _factual_summary = "\n".join(_factual_parts) if _factual_parts else "Action completed."
                        # Dynamic max_tokens from config (default 1024)
                        _response_tokens = 1024
                        if hasattr(ctx, "config") and ctx.config:
                            _response_tokens = ctx.config.get("user_settings.max_response_tokens") or ctx.config.get("max_response_tokens", 1024)
                        try:
                            _lang_hint = ""
                            _ulang = getattr(ctx, "_user_language_name", "")
                            if _ulang and _ulang.lower() != "english":
                                _lang_hint = f" Respond in {_ulang}."
                            _uid2 = str(getattr(ctx.user, "id", "")) if hasattr(ctx, "user") and ctx.user else ""
                            final_resp = await client.create_message(
                                max_tokens=_response_tokens,
                                system=f"Format the action results into a detailed, natural response.{_lang_hint} Describe what each function did with specifics from the results. Be thorough. No emojis.",
                                messages=[{"role": "user", "content": f"Action results:\n{_factual_summary}"}],
                                purpose="execution",
                                user_id=_uid2,
                            )
                            text = next((b.text for b in final_resp.content if hasattr(b, "text")), _factual_summary)
                        except Exception:
                            text = _factual_summary
                        text = enforce_os_identity(text)
                        text = enforce_response_style(text)
                        return self._make_chat_result(response=text, handled=True)
            return self._make_chat_result(response="Request required too many steps. Please simplify.", handled=bool(self._functions_called))
        except TaskCancelled:
            self._functions_called.append({
                "name": "__cancelled__", "params": {}, "action_type": "read",
                "success": False, "intercepted": False, "error": "Task cancelled by user",
                "event": "", "result": None,
            })
            return self._make_chat_result(response="Task cancelled.", task_cancelled=True, handled=bool(self._functions_called))
        except Exception as e:
            log.error(f"ChatExtension error: {e}")
            return self._make_chat_result(response=f"Error: {e}")
