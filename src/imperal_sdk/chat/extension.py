# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""ChatExtension — single entry point with LLM routing for extensions."""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    from imperal_sdk.runtime.executor import _check_target_scope
except ImportError:
    def _check_target_scope(**kwargs):
        return {"allowed": True, "cross_user": False}
from imperal_sdk.chat.action_result import ActionResult

log = logging.getLogger(__name__)


class TaskCancelled(Exception):
    """Raised by ctx.progress() when user cancels a task."""
    pass


ICNLI_INTEGRITY_RULES = """
ICNLI INTEGRITY RULES (enforced by kernel — you CANNOT ignore these):
- ALWAYS call a function for any data request. Never answer from memory or cached data.
- If a function returns an error, report the EXACT error to the user. Never pretend success.
- NEVER fabricate, invent, or guess data, URLs, links, tokens, or credentials.
- NEVER claim to have performed an action that a function did not confirm as successful.
- If NONE of your functions can handle the user's request, say "I can't do that right now." Do NOT mention other extensions, apps, or services by name.
- Respond in the user's language. No emojis. "Imperal" not "Imperial".
- After performing an action, confirm with ONE sentence what happened based on the function result.
"""


def _enforce_os_identity(text: str) -> str:
    """Kernel-level OS identity enforcement.

    Removes any sentences that redirect user to other extensions.
    Extensions are internal implementation — user sees only Imperal Cloud.
    """
    if not text:
        return text

    _redirect_phrases = (
        "extension", "расширение", "расширении",
        "handled by", "use the", "through the",
        "обрабатывается", "используйте",
    )
    _redirect_patterns = (
        "gmail extension", "notes extension", "admin extension",
        "sharelock extension", "mail extension", "case extension",
        "gmail app", "notes app", "another extension", "other extension",
        "separate extension", "different extension",
        "другое расширение", "другом расширении",
    )

    text_lower = text.lower()
    has_redirect = any(p in text_lower for p in _redirect_patterns)
    if not has_redirect:
        return text

    # Remove redirect sentences
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    for s in sentences:
        s_lower = s.lower()
        if any(p in s_lower for p in _redirect_patterns):
            log.info(f"OS Identity: stripped redirect sentence: {s[:80]}")
            continue
        cleaned.append(s)

    result = " ".join(cleaned).strip()
    return result if result else text


def _enforce_response_style(text: str) -> str:
    """Kernel-level response style enforcement. CODE, not prompt.

    1. Strips Unicode emojis (no extension should use them)
    2. Strips known filler/reassurance phrases
    3. Collapses excessive whitespace
    """
    if not text:
        return text
    import re
    # 1. Strip emojis (Unicode emoji ranges)
    text = re.sub(
        r'[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F'
        r'\u200D\u2702-\u27B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
        r'\u2B50\u26A0\u2B06\u2194-\u21AA]+', '', text
    )
    # 2. Strip known filler phrases (case-insensitive line removal)
    _filler = (
        "дайте знать", "let me know", "feel free to",
        "если вы хотите", "if you want to", "if you need",
        "ваши данные", "your data", "остаются сохранен",
        "в любой момент", "at any time", "anytime",
        "вы сможете снова", "you can re-enable", "you can always",
        "могу ещё чем-то помочь", "anything else",
        "что-то ещё", "чем-то помочь", "нужна ли", "нужно ли",
    )
    lines = text.split("\n")
    non_empty_lines = [l for l in lines if l.strip()]
    # Only strip filler if there are OTHER non-filler lines to keep
    # Never strip ALL lines — that results in empty response
    cleaned = []
    for line in lines:
        line_lower = line.strip().lower()
        if not line_lower:
            cleaned.append(line)
            continue
        if any(f in line_lower for f in _filler):
            # Check: would removing this leave us with zero content?
            remaining = [l for l in non_empty_lines if l.strip().lower() != line_lower and not any(f in l.strip().lower() for f in _filler)]
            if remaining:
                log.info(f"Response style: stripped filler: {line.strip()[:80]}")
                continue
            # else: this is the only meaningful line, keep it
        cleaned.append(line)
    text = "\n".join(cleaned)
    # 3. Collapse excessive blank lines (max 1)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Guard 1: Tool Result Trimmer ──────────────────────────────────────────
_KEEP_FIELDS = frozenset({
    "id", "message_id", "thread_id", "note_id", "from", "to", "cc", "bcc",
    "subject", "name", "email", "status", "RESULT", "error",
    "success", "sent", "archived", "deleted", "folder", "account",
    "note_id", "folder_id", "tag", "tags",
})
_TRIM_FIELDS = frozenset({
    "body", "content", "text", "html", "snippet", "preview",
    "description", "analysis", "summary", "message", "plain",
})


def _truncate_deep(obj, list_max: int = 5, str_max: int = 500):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        if len(obj) > list_max:
            trimmed = [_truncate_deep(item, list_max, str_max) for item in obj[:list_max]]
            trimmed.append(f"[...{len(obj) - list_max} more items]")
            return trimmed
        return [_truncate_deep(item, list_max, str_max) for item in obj]
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in _KEEP_FIELDS:
                result[k] = v
            elif k in _TRIM_FIELDS and isinstance(v, str) and len(v) > str_max:
                result[k] = v[:str_max] + f"... [{len(v)} chars total]"
            else:
                result[k] = _truncate_deep(v, list_max, str_max)
        return result
    return obj


def _trim_tool_result(content: str, max_tokens: int = 3000,
                      list_max: int = 5, str_max: int = 500) -> str:
    estimated_tokens = len(content) / 3
    if estimated_tokens <= max_tokens:
        return content
    max_chars = max_tokens * 3
    try:
        data = json.loads(content)
        trimmed = _truncate_deep(data, list_max, str_max)
        result = json.dumps(trimmed, ensure_ascii=False)
        if len(result) > max_chars:
            return result[:max_chars] + f"\n[...truncated, {len(content)} chars total]"
        return result
    except (json.JSONDecodeError, TypeError):
        pass
    return content[:max_chars] + f"\n[...truncated, {len(content)} chars total]"


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
                 action_type: str = "read", event: str = ""):
        """Register a chat function.

        Args:
            name: Function name (used in tool_use calls).
            description: What this function does (shown to LLM).
            params: Parameter definitions dict.
            action_type: "read", "write", or "destructive". Default "read".
                         Used by KAV for action verification and 2-step confirmation.
            event: Event name for ActionResult publishing (e.g. "mail.sent").
        """
        def decorator(func: Callable) -> Callable:
            self._functions[name] = FunctionDef(
                name=name, func=func, description=description,
                params=params or {}, action_type=action_type, event=event,
            )
            return func
        return decorator

    @property
    def functions(self) -> dict[str, FunctionDef]:
        return self._functions

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
        parts = [self.system_prompt, ICNLI_INTEGRITY_RULES]
        if hasattr(ctx, "skeleton_data") and ctx.skeleton_data:
            _ctx = ctx.skeleton_data.get("_context", {})
            cap = _ctx.get("_capability_boundary", {})
            if cap:
                others = [e["app_id"] for e in cap.get("other_extensions", [])]
                parts.append(f"\nCAPABILITY BOUNDARY: You are '{cap.get('you_are', '')}'. "
                    "You can ONLY use your available functions. If you cannot handle a request, say so briefly without mentioning other apps or services.")
            integrity = _ctx.get("_icnli_integrity", {})
            if integrity and integrity.get("rules"):
                parts.append("\nKERNEL INTEGRITY:\n" + "\n".join(f"- {r}" for r in integrity["rules"]))
        if hasattr(ctx, "user") and ctx.user:
            parts.append(f"\nCURRENT USER: {getattr(ctx.user, 'email', 'unknown')} (role: {getattr(ctx.user, 'role', 'user')})")
        return "\n".join(parts)

    def _build_messages(self, history: list, message: str,
                        context_window: int = 20, keep_recent: int = 6) -> list[dict]:
        messages = []
        windowed = (history or [])[-context_window:]
        n = len(windowed)

        for i, h in enumerate(windowed):
            role = h.get("role", "user")
            raw = h.get("content", "")
            text = raw if isinstance(raw, str) else str(raw)
            if not text:
                continue
            ts = h.get("ts", "")
            if ts:
                text = f"[{ts}] {text}"
            # Older messages: truncate long content
            is_recent = (n - i) <= keep_recent
            if not is_recent and len(text) > 500:
                text = text[:500] + "..."
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n" + text
            else:
                messages.append({"role": role, "content": text})

        messages.append({"role": "user", "content": message})
        if messages and messages[0]["role"] != "user":
            messages = messages[1:]
        return messages

    async def _handle(self, ctx, message: str = "", **kwargs) -> dict:
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

        # Per-extension tool rounds: config > constructor default > 10
        _max_tool_rounds = int(
            (ctx.config.get("context.max_tool_rounds") if hasattr(ctx, 'config') and ctx.config else None)
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
        if not tools: return {"response": "No functions registered", "_functions_called": self._functions_called, "_handled": False}
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

                resp = await client.create_message(model=self.model, max_tokens=2048, system=system, messages=messages, tools=tools, **_api_kwargs)
                tool_uses = [b for b in resp.content if b.type == "tool_use"]
                if not tool_uses:
                    text = next((b.text for b in resp.content if hasattr(b, "text")), "Done.")
                    text = _enforce_os_identity(text)
                    text = _enforce_response_style(text)
                    return {"response": text, "_functions_called": self._functions_called, "_handled": bool(self._functions_called)}
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

                    # 2-step confirmation: intercept write/destructive actions
                    if confirmation_required and action_type in ("write", "destructive"):
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
                            result = await _func_def.func(ctx, **tu.input)
                            _is_action_result = isinstance(result, ActionResult)
                            if _is_action_result:
                                content = json.dumps(result.to_dict(), default=str, ensure_ascii=False)
                            else:
                                content = json.dumps(result, default=str, ensure_ascii=False)
                                if _func_def.event:
                                    log.warning(f"ChatExtension {self.tool_name}: function '{tu.name}' has event='{_func_def.event}' but returned dict, not ActionResult")
                            content = _trim_tool_result(content, _max_result_tokens, _list_truncate_items, _string_truncate_chars)
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
                            content = _trim_tool_result(content, _max_result_tokens, _list_truncate_items, _string_truncate_chars)
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
                        content = _trim_tool_result(content, _max_result_tokens, _list_truncate_items, _string_truncate_chars)
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
                    return {
                        "response": "Action requires confirmation.",
                        "_functions_called": self._functions_called,
                        "_intercepted": True,
                    }

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
                        # KERNEL GUARANTEE: build factual response from function results ONLY.
                        # Do NOT ask Haiku for summary — it hallucinates state claims.
                        # This works for ALL extensions regardless of their prompts.
                        _factual_parts = []
                        for fc in self._functions_called:
                            if fc.get("intercepted"):
                                continue
                            _fname = fc.get("name", "action")
                            if fc.get("success"):
                                _params = fc.get("params", {})
                                _param_str = ", ".join(f"{k}={v}" for k, v in _params.items() if v) if _params else ""
                                _factual_parts.append(f"{_fname}({_param_str}): OK")
                            else:
                                _factual_parts.append(f"{_fname}: FAILED")
                        # Let Haiku format ONLY the factual results (no state claims allowed)
                        _factual_summary = "\n".join(_factual_parts) if _factual_parts else "Action completed."
                        try:
                            final_resp = await client.create_message(
                                model=self.model, max_tokens=256,
                                system="Format the action results into a brief, natural response in the user's language. ONLY describe what the functions DID. Do NOT claim any state you don't see in the results (e.g. never say 'no more items left' or 'all done' unless results explicitly confirm it). No emojis.",
                                messages=[{"role": "user", "content": f"Action results:\n{_factual_summary}"}],
                            )
                            text = next((b.text for b in final_resp.content if hasattr(b, "text")), _factual_summary)
                        except Exception:
                            text = _factual_summary
                        text = _enforce_os_identity(text)
                        text = _enforce_response_style(text)
                        return {"response": text, "_functions_called": self._functions_called, "_handled": True}
            return {"response": "Request required too many steps. Please simplify.", "_functions_called": self._functions_called, "_handled": bool(self._functions_called)}
        except TaskCancelled:
            self._functions_called.append({
                "name": "__cancelled__", "params": {}, "action_type": "read",
                "success": False, "intercepted": False, "error": "Task cancelled by user",
                "event": "", "result": None,
            })
            return {"response": "Task cancelled.", "_functions_called": self._functions_called, "_task_cancelled": True, "_handled": bool(self._functions_called)}
        except Exception as e:
            log.error(f"ChatExtension error: {e}")
            return {"response": f"Error: {e}", "_functions_called": self._functions_called, "_handled": False}
