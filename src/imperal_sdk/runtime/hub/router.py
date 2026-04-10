# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Hub router — LLM routing + message classification.

Single source of truth for all routing decisions.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

HUB_MODEL = os.getenv("HUB_MODEL", "claude-haiku-4-5-20251001")  # Legacy — model now resolved by LLM Provider from Panel config

MULTI_EXT_MIN_SCORE = 0.25
DOMINANCE_GAP = 0.12

# Valid intent types for KAV (Kernel Action Verification)
_VALID_INTENT_TYPES = {"read", "write", "destructive"}

# Executor result types that Hub must pass through to session_workflow unchanged.
_PASSTHROUGH_TYPES = {"task_promoted", "confirmation", "task_limit_reached"}

# Patterns that indicate multi-topic queries
_MULTI_TOPIC_PATTERN = re.compile(
    r'\b(and|и|а также|плюс|plus)\b|'
    r',\s*(all|show|list|my|мои|все|покажи)',
    re.IGNORECASE,
)
# Patterns that indicate user asks about system capabilities
_CAPABILITIES_PATTERN = re.compile(
    r'\b(what can you do|what are your capabilities|что ты умеешь|'
    r'what are all|your capabilities|all of your capabilities|'
    r'что ты можешь)\b',
    re.IGNORECASE,
)


def _get_llm():
    """Get LLM provider singleton."""
    from imperal_sdk.runtime.llm_provider import get_llm_provider
    return get_llm_provider()


def _is_extension_error(text: str) -> bool:
    """Code-based error detection. No LLM. Deterministic."""
    if not isinstance(text, str) or len(text) < 5:
        return False
    t = text.lower()
    return any(p in t for p in (
        "an error occurred while processing",
        "extension error", "not available", "is not available",
        "not connected", "connect first",
        "access denied",
    ))


def _is_capabilities_query(message: str) -> bool:
    """Detect if user is asking about system-wide capabilities."""
    return bool(_CAPABILITIES_PATTERN.search(message))


def _is_short_ack(message: str) -> bool:
    """Detect short acknowledgments/dismissals that should NEVER dispatch to extensions.
    These are conversational fillers — always navigate, never function call."""
    _msg = message.strip().lower()
    _ack_words = {
        # Russian
        'не', 'нет', 'да', 'ок', 'окей', 'ладно', 'понял', 'понятно', 'хорошо',
        'спасибо', 'благодарю', 'пока', 'привет', 'здравствуйте', 'круто', 'супер',
        'отлично', 'ясно', 'угу', 'ага', 'неа', 'норм', 'збс', 'ну',
        # English
        'no', 'yes', 'ok', 'okay', 'sure', 'thanks', 'thank', 'bye', 'hi', 'hello',
        'hey', 'nope', 'yep', 'yeah', 'nah', 'cool', 'great', 'fine', 'got it',
        'alright', 'right', 'nice', 'wow', 'hmm', 'hm',
        # French/German/Spanish basics
        'non', 'oui', 'merci', 'salut', 'nein', 'ja', 'danke', 'hola', 'gracias', 'si',
    }
    words = _msg.split()
    if len(words) <= 2:
        if all(w.rstrip('!?.,:;') in _ack_words for w in words):
            return True
    stripped = _msg.strip('!?.,:; ')
    if not stripped:
        return True
    return False


def _is_multi_topic(message: str) -> bool:
    """Detect if message explicitly mentions multiple topics (conjunctions, commas)."""
    return bool(_MULTI_TOPIC_PATTERN.search(message))


async def _route_with_llm(message: str, catalog: Any, history: list | None = None, user_id: str = "", allowed_apps: set | None = None, session_hint: str = "", routing_context: int = 12) -> tuple[list[str], str, str]:
    """LLM-based routing — Haiku decides which extension(s) handle this message
    and classifies the user's intent type for KAV (Kernel Action Verification).
    
    PRIMARY and ONLY router. Single source of truth for all routing decisions.
    Works in ANY language, understands nuanced intent.
    Cost: ~$0.0005, ~150ms.
    
    Returns:
        tuple of (app_ids list, intent_type string, language string).
        intent_type is one of: "read", "write", "destructive".
        language is ISO 639-1 code (e.g. "ru", "en").
        Defaults to ("read", "") if classification fails.
    """
    if not catalog or not catalog.loaded:
        return [], "read", ""
    
    ext_descriptions = []
    _seen_apps = set()
    for t in catalog.tools:
        _app = t["app_id"]
        if _app in _seen_apps:
            continue
        _seen_apps.add(_app)
        if allowed_apps is not None and _app not in allowed_apps:
            continue
        ext_descriptions.append(f"- {_app}: {t.get('description', t.get('name', ''))[:150]}")
    ext_list = "\n".join(ext_descriptions)
    
    try:
        _session_hint = session_hint

        provider = _get_llm()
        resp = await provider.create_message(
            max_tokens=50,
            purpose="routing",
            user_id=user_id,
            messages=[{"role": "user", "content": f"""Which extension(s) should handle this user message? Also classify the intent type.

AVAILABLE EXTENSIONS:
{ext_list}

USER MESSAGE: "{message}"
{('RECENT CONVERSATION CONTEXT (most recent last):' + chr(10) + chr(10).join(h.get("role","").upper() + ": " + h.get("content","")[:800] for h in (history or [])[-routing_context:])) if history else ""}
{_session_hint}

Rules:
- ACTION follow-ups like "do it", "go ahead", "send it", "yes send", "давай", "отправь" are FOLLOW-UPS. Route to the SAME extension.
- For email operations (send, read, inbox, reply, compose, show emails, list emails) → gmail
- For case management, investigation, analysis → sharelock-v2
- For notes (create, list, search, delete notes) → notes
- For user/role/extension management, system health, AI Cloud Agents (automations/rules), platform config → admin
- For creating/managing automated agents, scheduling tasks, setting up triggers → admin
- IMPORTANT: enable/disable/activate/suspend/включи/выключи/верни operations on extensions or users → ALWAYS admin (even short follow-ups like "включи обратно", "enable it back", "turn it on")
- For multiple topics (emails AND cases) → list both
- If truly unclear → pick the most likely ONE

CRITICAL CONVERSATIONAL DETECTION (ANY language):
- Greetings (Привет, Hello, Bonjour, こんにちは, مرحبا, Hola, Hi, Hey, Здравствуйте) → ALWAYS "none"
- Thanks (Спасибо, Thank you, Merci, ありがとう, شكرا, Gracias, Thanks, Благодарю) → ALWAYS "none"
- Acknowledgments/Dismissals (Ок, Понятно, Хорошо, OK, Got it, Sure, Ладно, Ясно, Alright, Не, Нет, Неа, No, Nope, Nah, Круто, Nice, Cool) → ALWAYS "none"
- Farewells (Пока, Bye, До свидания, Goodbye, See you, さようなら) → ALWAYS "none"
- General questions about the system (what can you do, что умеешь) → "none"
- These are NEVER follow-ups to extensions, regardless of session context.
- When in doubt about a short message: if it has NO action verb → "none"
- ACTION follow-ups ("do it", "send it", "давай", "отправь") WITH a LAST USED EXTENSION → route to that extension

Intent classification:
- READ = viewing, listing, searching, checking status (no changes)
- WRITE = sending, creating, updating, replying, saving (makes changes)
- DESTRUCTIVE = deleting, removing, suspending, revoking, trashing (irreversible changes)
- IMPORTANT: delete/remove/удали/trash/suspend = ALWAYS DESTRUCTIVE, never WRITE

Also detect the LANGUAGE of the user's message (ISO 639-1 code).

Answer format: app_id1,app_id2|INTENT_TYPE|LANG_CODE
Examples: gmail|WRITE|ru, admin,gmail|WRITE|en, gmail|READ|es, admin|DESTRUCTIVE|fr, none|READ|ru
LANG_CODE: 2-letter ISO 639-1 (ru, en, es, fr, de, ar, zh, ja, ko, pt, it, tr, etc.)
Nothing else."""}],
        )
        answer = resp.content[0].text.strip().lower() if resp.content else ""
        
        intent_type = "read"
        _llm_language = ""
        apps_part = answer
        _pipe_parts = answer.split("|")
        if len(_pipe_parts) >= 3:
            apps_part = _pipe_parts[0].strip()
            raw_intent = _pipe_parts[1].strip()
            _llm_language = _pipe_parts[2].strip()
            if raw_intent in _VALID_INTENT_TYPES:
                intent_type = raw_intent
        elif len(_pipe_parts) == 2:
            apps_part = _pipe_parts[0].strip()
            raw_intent = _pipe_parts[1].strip()
            if raw_intent in _VALID_INTENT_TYPES:
                intent_type = raw_intent
        
        app_ids = [a.strip() for a in apps_part.replace("\n", ",").split(",") if a.strip()]
        if app_ids == ["none"] or (len(app_ids) == 1 and app_ids[0] == "none"):
            log.info(f"Hub LLM routing: '{message[:50]}' → navigate (none) lang={_llm_language}")
            return [], intent_type, _llm_language
        valid_apps = {t["app_id"] for t in catalog.tools}
        result = [a for a in app_ids if a in valid_apps]
        if result:
            log.info(f"Hub LLM routing: '{message[:50]}' → {result} (intent={intent_type}, lang={_llm_language})")
            return result, intent_type, _llm_language
    except Exception as e:
        log.warning(f"Hub LLM routing failed: {e}")
        _err_str = str(e).lower()
        if any(x in _err_str for x in ('502', '503', '500', 'connection', 'timeout', 'unavailable', 'failover disabled')):
            raise
    
    return [], "read", ""


def _detect_automation_target(message: str, extensions: dict) -> str | None:
    """Determine target extension for automation action from message content.
    
    Direct keyword matching — more reliable than embeddings for automation.
    Returns app_id or None if ambiguous.
    """
    msg = message.lower()
    
    if any(w in msg for w in ["send email", "reply email", "send reply", "compose email", "reply to email",
                               "forward email", "inbox", "gmail", "mail to"]):
        if "gmail" in extensions:
            return "gmail"
    
    if any(w in msg for w in ["create case", "case", "investigation", "analysis",
                               "sharelock", "document analysis"]):
        if "sharelock-v2" in extensions:
            return "sharelock-v2"
    
    if any(w in msg for w in ["create note", "note", "save note", "notes"]):
        if "notes" in extensions:
            return "notes"
    
    if any(w in msg for w in ["system health", "list users", "list extensions",
                               "suspend", "activate", "create user", "delete user",
                               "show users", "show extensions", "automation"]):
        if "admin" in extensions:
            return "admin"
    
    return None


def _select_dispatch_targets(extensions: dict, message: str = "") -> dict:
    """Determine which extensions to dispatch to.

    Rules (in priority order):
    1. If only 1 extension → return it (fast path)
    2. If message is multi-topic → return ALL extensions above 0.15
    3. If top extension dominates → single dispatch
    4. If 2+ extensions with similar high scores → multi dispatch
    5. Fallback → top extension only
    """
    if len(extensions) <= 1:
        return extensions

    sorted_exts = sorted(extensions.items(), key=lambda x: x[1].get("relevance", 0), reverse=True)
    top_app, top_candidate = sorted_exts[0]
    top_score = top_candidate.get("relevance", 0)
    second_score = sorted_exts[1][1].get("relevance", 0) if len(sorted_exts) > 1 else 0

    if _is_multi_topic(message) and len(extensions) >= 2:
        multi_targets = {app: cand for app, cand in extensions.items()
                        if cand.get("relevance", 0) >= 0.15}
        if len(multi_targets) >= 2:
            log.info(f"Hub multi-topic detected: dispatching to ALL {list(multi_targets.keys())}")
            return multi_targets

    if top_score - second_score > DOMINANCE_GAP:
        log.info(f"Hub dominance: {top_app}({top_score:.3f}) >> second({second_score:.3f}), single dispatch")
        return {top_app: top_candidate}

    multi_targets = {}
    for app_id, candidate in sorted_exts:
        score = candidate.get("relevance", 0)
        if score >= MULTI_EXT_MIN_SCORE:
            multi_targets[app_id] = candidate

    if len(multi_targets) >= 2:
        log.info(f"Hub multi-dispatch: {list(multi_targets.keys())} (similar scores)")
        return multi_targets

    return {top_app: top_candidate}
