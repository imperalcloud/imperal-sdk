# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Hub navigator — navigation mode + result combining."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from imperal_sdk.runtime.hub.session import _get_hub_redis
from imperal_sdk.runtime.hub.router import _get_llm

log = logging.getLogger(__name__)


async def _hub_navigate(message: str, history: list, user_info: dict, catalog: Any, allowed_apps: set | None = None, context: dict | None = None, skeleton: dict | None = None, routing_context: int = 12) -> dict:
    """Navigation mode — conversational assistant when no extension matches."""
    capabilities = []
    user_scopes = user_info.get("scopes", ["*"])
    _user_id = user_info.get("id", "")

    _allowed_apps = allowed_apps

    if catalog and catalog.loaded:
        ext_tools = {}
        for t in catalog.tools:
            app_id = t.get("app_id", "")
            if _allowed_apps is not None and app_id not in _allowed_apps:
                continue
            app = t.get("app_display_name", t.get("app_id", "unknown"))
            desc = t.get("description", t.get("name", ""))
            ext_tools.setdefault(app, []).append(desc)
        for app_name, tools in ext_tools.items():
            tool_list = "; ".join(t for t in tools if t)
            capabilities.append(f"- **{app_name}**: {tool_list}" if tool_list else f"- **{app_name}**")
        _has_auto = "*" in user_scopes or "automations:*" in user_scopes or "automations:read" in user_scopes
        if _has_auto:
            capabilities.append("- **Automations**: create, list, pause, resume, and delete automation rules")

    capabilities_text = "\n".join(capabilities) if capabilities else "No extensions installed."
    user_email = user_info.get("email", "unknown")

    # ── Fresh time calculation (never stale) ──────────────────────
    _user_tz_str = "UTC"
    _ui_attrs = user_info.get("attributes", {})
    _assistant_name = "Webbee"
    _assistant_avatar = ""
    try:
        _hr = await _get_hub_redis()
        _assistant_raw = await _hr.get("imperal:platform:assistant")
        if _assistant_raw:
            import json as _json_assist
            _assist_data = _json_assist.loads(_assistant_raw)
            _assistant_name = _assist_data.get("name", "Webbee")
            _assistant_avatar = _assist_data.get("avatar", "")
    except Exception:
        pass
    if isinstance(_ui_attrs, dict) and _ui_attrs.get("timezone"):
        _user_tz_str = _ui_attrs["timezone"]
    if _user_tz_str == "UTC" and context:
        _time_ctx = context.get("_time", {})
        if isinstance(_time_ctx, dict):
            _user_tz_str = _time_ctx.get("timezone") or _user_tz_str
        elif hasattr(_time_ctx, "timezone") and _time_ctx.timezone:
            _user_tz_str = _time_ctx.timezone
    if _user_tz_str == "UTC" and skeleton and isinstance(skeleton, dict):
        for _section in skeleton.values():
            if isinstance(_section, dict) and _section.get("timezone"):
                _user_tz_str = _section["timezone"]
                break
    try:
        _tz = ZoneInfo(_user_tz_str)
    except Exception:
        _tz = ZoneInfo("UTC")
    _now = datetime.now(timezone.utc).astimezone(_tz)
    _has_auto = "*" in user_scopes or "automations:*" in user_scopes or "automations:read" in user_scopes
    if _has_auto:
        _automations_section = """
AI CLOUD AGENTS (automation power):
Users can create intelligent agents that run automatically:
- Cron-based schedules, event-driven triggers, multi-step workflows
- Direct + Agent steps: zero-LLM function calls + intelligent dispatch
- Template variables: steps can reference previous step results
When users ask about automation ideas — suggest combinations of the tools from YOUR CAPABILITIES above."""
    else:
        _automations_section = ""

    _time_line = f"\nCurrent time: {_now.strftime('%Y-%m-%d %H:%M')} ({_user_tz_str})"

    system_prompt = f"""You are Imperal Cloud — the world's first AI Cloud Operating System powered by ICNLI (Natural Language + Deep Context + Real Actions + Safety).

You are {_assistant_name} — the AI assistant of Imperal Cloud. You are intelligent, proactive, and confident.

CURRENT USER: {user_email}{_time_line}

YOUR CAPABILITIES (real, from live catalog):
{capabilities_text}

WHAT YOU CAN DO:
- Execute ONLY actions listed in YOUR CAPABILITIES above. You have NO other capabilities.
- Chain multiple actions from your catalog in one request
- Work in ANY language — Russian, English, French, Chinese, Arabic, etc.
{_automations_section}

CONVERSATION RULES:
1. You ARE Imperal Cloud. NEVER say "I'm the Notes helper" or "ask extension X". ALL capabilities are YOURS.
2. If the user's request needs action (show emails, create note, etc.) — tell them to send their request directly and you will execute it. Be helpful, not bureaucratic.
3. NEVER fabricate data. Only describe capabilities you actually have from the catalog.
4. Respond in the user's language. No emojis. "Imperal" not "Imperial". ALWAYS use Markdown formatting (bold, lists, headers).
5. Be confident, concise, and proactive. Suggest what you can do. Offer next steps.
6. NEVER mention internal routing, extensions by name, or technical architecture.
7. When user says thanks/goodbye — respond briefly and warmly. No function calls needed.
8. When asked "what can you do?" — describe ONLY capabilities from YOUR CAPABILITIES section above. NEVER mention features not in your catalog.
9. Be PROACTIVE: if user shows interest in a topic, suggest related actions. "Показать письма? Хочешь чтобы я также проверил непрочитанные?"
10. For greetings: introduce yourself briefly, mention your key capabilities, and ask what the user needs. Include current time if relevant.
11. LANGUAGE: ALWAYS respond in the SAME language as the user's message. Russian message → Russian response. English → English. NEVER mix languages. This is non-negotiable.
12. NO EMOJIS. Never use emoji characters. Professional tone only.
13. CRITICAL: NEVER describe or suggest capabilities not listed in YOUR CAPABILITIES. If a user asks about a feature not in your catalog, say you cannot help with that. NEVER assume admin, cases, or other features exist unless they appear in YOUR CAPABILITIES.
14. FORMATTING: ALWAYS use Markdown formatting. Use **bold** for labels/names, bullet lists for items, numbered lists for steps, `code` for IDs/emails. Structure ALL responses with clear visual hierarchy. NEVER output plain text walls.
15. ID INTEGRITY: When suggesting actions on specific items, ALWAYS reference them by their exact ID from function results. NEVER construct or guess IDs."""

    messages = []
    for h in (history or [])[-routing_context:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    _nav_lang = context.get("_user_language", "") if context else ""
    _nav_lang_name = context.get("_user_language_name", "") if context else ""
    _nav_msg = message
    if _nav_lang and _nav_lang != "en" and _nav_lang_name:
        _nav_msg = f"{message}\n[RESPOND IN {_nav_lang_name.upper()} ONLY]"
    messages.append({"role": "user", "content": _nav_msg})

    try:
        provider = _get_llm()
        resp = await provider.create_message(
            max_tokens=1024,
            purpose="navigation",
            user_id=user_info.get("id", ""),
            system=system_prompt,
            messages=messages,
        )
        text = resp.content[0].text if resp.content else "Hello! How can I help you?"
        import re as _re
        text = _re.sub(
            r'[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F'
            r'\u200D\u2702-\u27B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
            r'\u2B50\u26A0\u2B06\u2194-\u21AA]+', '', text
        )
        return {"response": text.strip()}
    except Exception as e:
        log.error(f"Hub navigate error: {e}")
        _err_str = str(e).lower()
        if any(x in _err_str for x in ("502", "503", "500", "connection", "timeout", "unavailable", "failover disabled")):
            return {"response": "**AI model is currently unavailable.** Check your LLM provider settings or enable platform fallback in Settings > AI Provider.", "_error": True}
        return {"response": f"Hello! I'm {_assistant_name}, the Imperal Cloud assistant. How can I help you?"}


async def _hub_combine(message: str, results: dict, user_info: dict) -> dict:
    """Combine results from multiple extensions into one response."""
    if len(results) == 1:
        return {"response": next(iter(results.values()))}

    results_text = ""
    for app_id, data in results.items():
        results_text += f"\n[{app_id}]:\n{data}\n"

    system_prompt = """You are combining results from multiple ICNLI OS chain steps into one response.
RULES:
- Include ALL data from results. Do not omit anything.
- Do NOT add information not present in the results.
- Do NOT fabricate data. If a result contains an error, show the error.
- Format cleanly. Use the user's language. No emojis. "Imperal" not "Imperial".
- Structure the response with CLEAR STEP LABELS showing what was done at each step.
  Use descriptive labels based on the ACTION, not the extension name.
  Examples: "Email Summary", "Note Created", "Email Sent", "Analysis Results".
- Use markdown headers (##) or bold (**label:**) for each step's results.
- If one step couldn't handle part of the query, show the error under its label.
- NEVER mention extension names (gmail, notes, admin, sharelock). Use action descriptions instead."""

    try:
        provider = _get_llm()
        resp = await provider.create_message(
            max_tokens=2048,
            purpose="navigation",
            user_id=user_info.get("id", ""),
            system=system_prompt,
            messages=[{"role": "user", "content": f"User asked: {message}\n\nExtension results:{results_text}"}],
        )
        text = resp.content[0].text if resp.content else next(iter(results.values()))
        return {"response": text}
    except Exception as e:
        log.error(f"Hub combine error: {e}")
        combined = "\n\n".join(f"**{app}:** {data}" for app, data in results.items())
        return {"response": combined}
