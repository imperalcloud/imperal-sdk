"""ICNLI OS Hub — kernel-level cross-app orchestrator.

The Hub is the OS shell. It discovers, dispatches, and combines results
from multiple extensions in a single user request. Like Unix bash — part
of the kernel, not an extension.

5-step algorithm: DISCOVER → DISPATCH → TRIAGE → RETRY → COMBINE

Dispatch rules:
- Capabilities query → navigation mode (show ALL capabilities)
- Multi-topic message (and/и/commas) → multi dispatch (all scored > 0.15)
- One dominant extension (score >> others) → single dispatch
- Two+ extensions with similar high scores → parallel dispatch
- No match from embeddings → LLM routing fallback
- Still no match → navigation mode (read-only shell)
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Kernel response enforcement (strips emojis, filler)
try:
    from imperal_sdk.chat.extension import _enforce_response_style
except ImportError:
    _enforce_response_style = lambda t: t


import time as _time
import redis.asyncio as _aioredis

_hub_redis = None
_HUB_SESSION_TTL = 3600
_FOLLOWUP_MAX_WORDS = 6
_FOLLOWUP_STALE_SECONDS = 600

# FAST PATH threshold: embeddings score >= this → skip LLM routing (saves ~200ms).
# Below this → LLM routing decides (Haiku is multilingual, handles any language).
# _FAST_PATH_THRESHOLD removed (2026-04-08) — Haiku always runs

async def _get_hub_redis():
    global _hub_redis
    if _hub_redis is None:
        _hub_redis = _aioredis.from_url(
            os.getenv("REDIS_URL", ""), decode_responses=True
        )
    return _hub_redis

async def _load_session_state(user_id: str) -> dict:
    """Load Hub session state from Redis. Returns {} if none or stale."""
    try:
        r = await _get_hub_redis()
        raw = await r.get(f"imperal:hub_session:{user_id}")
        if not raw:
            return {}
        state = json.loads(raw)
        if _time.time() - state.get("ts", 0) > _FOLLOWUP_STALE_SECONDS:
            return {}
        return state
    except Exception:
        return {}

async def _save_session_state(user_id: str, app_id: str, result: dict):
    """Save Hub session state after extension dispatch. Kernel-level, automatic."""
    try:
        r = await _get_hub_redis()
        response = result.get("response", "") if isinstance(result, dict) else str(result)
        fc_list = result.get("_functions_called", []) if isinstance(result, dict) else []
        last_fn = fc_list[-1].get("name", "") if fc_list else ""
        
        import re as _re
        referenced_ids = _re.findall(r'(?:ID|id)[:\s]+([a-zA-Z0-9_-]{8,})', response)
        
        state = {
            "last_app": app_id,
            "last_function": last_fn,
            "referenced_ids": referenced_ids[:10],
            "response_preview": response[:300],
            "ts": _time.time(),
        }
        await r.setex(
            f"imperal:hub_session:{user_id}",
            _HUB_SESSION_TTL,
            json.dumps(state, ensure_ascii=False),
        )
    except Exception as e:
        log.debug(f"Session state save failed (non-blocking): {e}")


def _build_chain_step_context(step_index: int, all_results: list) -> str:
    """Guard 5: Build condensed context for chain step N from previous results.

    Immediately previous step: full result (up to 2000 chars).
    Older steps: one-line summary (200 chars).
    """
    if not all_results:
        return ""
    parts = []
    for i, (app_id, result) in enumerate(all_results):
        text = result.get("response", "") if isinstance(result, dict) else str(result)
        if i == step_index - 1:
            if len(text) > 2000:
                text = text[:2000] + "..."
            parts.append(f"[Previous step ({app_id}): {text}]")
        else:
            summary = text[:200] + "..." if len(text) > 200 else text
            parts.append(f"[Step {i+1} ({app_id}): {summary}]")
    return "\n".join(parts)

HUB_MODEL = os.getenv("HUB_MODEL", "claude-haiku-4-5-20251001")

MULTI_EXT_MIN_SCORE = 0.25
DOMINANCE_GAP = 0.12

# Valid intent types for KAV (Kernel Action Verification)
_VALID_INTENT_TYPES = {"read", "write", "destructive"}

# Executor result types that Hub must pass through to session_workflow unchanged.
# These are kernel-level signals (task promotion, confirmation cards) that
# session_workflow handles directly — Hub must NOT strip them to strings.
_PASSTHROUGH_TYPES = {"task_promoted", "confirmation", "task_limit_reached"}

# Patterns that indicate multi-topic queries (user wants data from MULTIPLE extensions)
_MULTI_TOPIC_PATTERN = re.compile(
    r'\b(and|и|а также|плюс|plus)\b|'  # conjunctions
    r',\s*(all|show|list|my|мои|все|покажи)',  # comma + action word
    re.IGNORECASE,
)
# Patterns that indicate user asks about system capabilities (should go to navigate)
_CAPABILITIES_PATTERN = re.compile(
    r'\b(what can you do|what are your capabilities|что ты умеешь|'
    r'what are all|your capabilities|all of your capabilities|'
    r'что ты можешь)\b',
    re.IGNORECASE,
)

async def _enrich_if_followup(message: str, user_id: str) -> str:
    """Kernel-level follow-up enrichment. Deterministic, no LLM.
    
    Short messages (<=6 words) + recent session state = follow-up.
    Injects structured context from last extension call into the message.
    """
    words = message.strip().split()
    if len(words) > _FOLLOWUP_MAX_WORDS:
        return message

    state = await _load_session_state(user_id)
    if not state:
        return message

    parts = []
    if state.get("last_app"):
        parts.append(f"last_extension={state['last_app']}")
    if state.get("last_function"):
        parts.append(f"last_function={state['last_function']}")
    if state.get("referenced_ids"):
        parts.append(f"referenced_ids={','.join(state['referenced_ids'][:5])}")
    if state.get("response_preview"):
        parts.append(f"previous_response={state['response_preview'][:200]}")
    
    if not parts:
        return message
    
    context_block = " | ".join(parts)
    enriched = f"{message}\n\n[KERNEL CONTEXT: {context_block}]"
    log.info(f"Hub follow-up enrichment: '{message[:40]}' + {len(parts)} context fields")
    return enriched

def _strip_kernel_context(text: str) -> str:
    """Remove [KERNEL CONTEXT: ...] from response text. LLM may echo it back."""
    import re
    return re.sub(r'\s*\[KERNEL CONTEXT:[^\]]*\]', '', text).strip()


async def _update_chain_status(user_id: str, context: dict, status_text: str):
    """Update chat status_text directly from Hub during chain execution.
    Kernel-level: writes to Redis so frontend polling picks it up."""
    assistant_msg_id = context.get("assistant_message_id")
    if not assistant_msg_id:
        return
    try:
        r = await _get_hub_redis()
        history_key = f"imperal:hub:chat:{user_id}"
        existing = await r.get(history_key)
        if not existing:
            return
        messages = json.loads(existing)
        for msg in messages:
            if msg.get("id") == assistant_msg_id and msg.get("status") == "processing":
                msg["status_text"] = status_text
                break
        await r.set(history_key, json.dumps(messages, ensure_ascii=False), ex=86400)
    except Exception:
        pass  # Best effort

def _get_llm():
    """Get LLM provider singleton (Anthropic or OpenAI-compatible)."""
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
    # Single-word acks in multiple languages
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
    # Check single word or very short (1-2 words)
    words = _msg.split()
    if len(words) <= 2:
        # Check if ALL words are ack words
        if all(w.rstrip('!?.,:;') in _ack_words for w in words):
            return True
    # Also catch emoji-only or punctuation-only
    stripped = _msg.strip('!?.,:; ')
    if not stripped:
        return True
    return False


_LANG_NAMES = {
    "ru": "Russian", "en": "English", "es": "Spanish", "fr": "French",
    "de": "German", "ar": "Arabic", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "pt": "Portuguese", "it": "Italian", "tr": "Turkish",
}


def _is_multi_topic(message: str) -> bool:
    """Detect if message explicitly mentions multiple topics (conjunctions, commas)."""
    return bool(_MULTI_TOPIC_PATTERN.search(message))

async def _route_with_llm(message: str, catalog, history: list = None, user_id: str = "", allowed_apps: set = None) -> tuple[list[str], str]:
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
    
    # Build extension list for Haiku
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
        _session_hint = ""
        if user_id:
            _ss = await _load_session_state(user_id)
            if _ss.get("last_app"):
                _session_hint = f"\nLAST USED EXTENSION: {_ss['last_app']}"

        provider = _get_llm()
        resp = await provider.create_message(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": f"""Which extension(s) should handle this user message? Also classify the intent type.

AVAILABLE EXTENSIONS:
{ext_list}

USER MESSAGE: "{message}"
{('RECENT CONVERSATION CONTEXT (most recent last):' + chr(10) + chr(10).join(h.get("role","").upper() + ": " + h.get("content","")[:500] for h in (history or [])[-6:])) if history else ""}
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
        
        # Parse intent_type + language from pipe separators
        # Format: app_ids|INTENT|LANG (e.g. "gmail|WRITE|ru")
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
        
        # Parse app_ids
        app_ids = [a.strip() for a in apps_part.replace("\n", ",").split(",") if a.strip()]
        # Handle "none" → navigate mode (greetings, general conversation)
        if app_ids == ["none"] or (len(app_ids) == 1 and app_ids[0] == "none"):
            log.info(f"Hub LLM routing: '{message[:50]}' → navigate (none) lang={_llm_language}")
            return [], intent_type, _llm_language
        # Validate against catalog
        valid_apps = {t["app_id"] for t in catalog.tools}
        result = [a for a in app_ids if a in valid_apps]
        if result:
            log.info(f"Hub LLM routing: '{message[:50]}' → {result} (intent={intent_type}, lang={_llm_language})")
            return result, intent_type, _llm_language
    except Exception as e:
        log.warning(f"Hub LLM routing failed: {e}")
    
    return [], "read", ""

def _detect_automation_target(message: str, extensions: dict) -> str | None:
    """Determine target extension for automation action from message content.
    
    Direct keyword matching — more reliable than embeddings for automation.
    Returns app_id or None if ambiguous.
    """
    msg = message.lower()
    
    # Email operations → gmail
    if any(w in msg for w in ["send email", "reply email", "send reply", "compose email", "reply to email",
                               "forward email", "inbox", "gmail", "mail to"]):
        if "gmail" in extensions:
            return "gmail"
    
    # Case operations → sharelock
    if any(w in msg for w in ["create case", "case", "investigation", "analysis",
                               "sharelock", "document analysis"]):
        if "sharelock-v2" in extensions:
            return "sharelock-v2"
    
    # Note operations → notes
    if any(w in msg for w in ["create note", "note", "save note", "notes"]):
        if "notes" in extensions:
            return "notes"
    
    # Admin operations → admin
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
    2. If message is multi-topic (and/и/commas) → return ALL extensions above 0.15 (user explicitly wants multiple)
    3. If top extension dominates (score >> second by DOMINANCE_GAP) → single dispatch
    4. If 2+ extensions with similar high scores (both > 0.25) → multi dispatch
    5. Fallback → top extension only
    """
    if len(extensions) <= 1:
        return extensions

    sorted_exts = sorted(extensions.items(), key=lambda x: x[1].get("relevance", 0), reverse=True)
    top_app, top_candidate = sorted_exts[0]
    top_score = top_candidate.get("relevance", 0)
    second_score = sorted_exts[1][1].get("relevance", 0) if len(sorted_exts) > 1 else 0

    # Rule 2: Multi-topic message → dispatch to ALL matched extensions
    if _is_multi_topic(message) and len(extensions) >= 2:
        multi_targets = {app: cand for app, cand in extensions.items()
                        if cand.get("relevance", 0) >= 0.15}
        if len(multi_targets) >= 2:
            log.info(f"Hub multi-topic detected: dispatching to ALL {list(multi_targets.keys())}")
            return multi_targets

    # Rule 3: Dominance check
    if top_score - second_score > DOMINANCE_GAP:
        log.info(f"Hub dominance: {top_app}({top_score:.3f}) >> second({second_score:.3f}), single dispatch")
        return {top_app: top_candidate}

    # Rule 4: Similar high scores
    multi_targets = {}
    for app_id, candidate in sorted_exts:
        score = candidate.get("relevance", 0)
        if score >= MULTI_EXT_MIN_SCORE:
            multi_targets[app_id] = candidate

    if len(multi_targets) >= 2:
        log.info(f"Hub multi-dispatch: {list(multi_targets.keys())} (similar scores)")
        return multi_targets

    # Rule 5: Fallback to top
    return {top_app: top_candidate}

async def _plan_chain_steps(message: str, app_ids: list[str]) -> list[tuple[str, str]]:
    """Single LLM call: plan chain steps with order + per-step messages.
    
    Returns ordered list of (app_id, step_message) tuples.
    Same extension CAN appear multiple times (e.g. gmail read → notes → gmail send).
    Cost: ~$0.0005, ~150ms.
    """
    if len(app_ids) <= 1:
        return [(app_ids[0], message)] if app_ids else []
    
    apps_str = ", ".join(app_ids)
    try:
        provider = _get_llm()
        resp = await provider.create_message(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": f"""Break this user request into sequential execution steps. Each step is handled by ONE extension.

AVAILABLE EXTENSIONS: {apps_str}
USER REQUEST: "{message}"

RULES:
- Each step must be a clear, actionable sub-task for ONE extension
- Data-producing steps FIRST (read emails, list data)
- Data-saving steps SECOND (create notes, save records)
- Communication steps LAST (send emails, forward)
- An extension CAN appear MULTIPLE TIMES if the request needs it at different stages
  (e.g. "read emails then send summary" = gmail:read, notes:save, gmail:send)
- Each step message must be self-contained and clear

FORMAT (one step per line, numbered):
1. app_id: step description
2. app_id: step description

Example: "summarize my 5 emails, make a note, and email the results to bob@mail.com"
1. gmail: read the first 5 emails from inbox and create a summary of each
2. notes: create a note titled "Email Summary" with the summaries from the previous step
3. gmail: send an email to bob@mail.com with the complete email summaries and note content

Plan the steps now:"""}],
        )
        answer = resp.content[0].text.strip() if resp.content else ""
        
        steps = []
        for line in answer.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Remove numbering (1. 2. etc)
            import re as _re
            line = _re.sub(r'^\d+\.\s*', '', line)
            if ":" not in line:
                continue
            parts = line.split(":", 1)
            app_id = parts[0].strip().lower()
            step_msg = parts[1].strip()
            if app_id in app_ids and step_msg:
                steps.append((app_id, step_msg))
        
        if steps:
            log.info(f"Hub chain steps: {[(s[0], s[1][:40]) for s in steps]}")
            return steps
    except Exception as e:
        log.warning(f"Hub chain planning failed: {e}")
    
    # Fallback: each extension gets full message, data producers first
    return [(aid, message) for aid in app_ids]

def _is_passthrough(result) -> bool:
    """Check if executor result is a kernel signal that must pass through Hub unchanged."""
    return isinstance(result, dict) and result.get("type") in _PASSTHROUGH_TYPES

async def handle_hub_chat(tool_input: dict, execute_fn, catalog, relations: dict) -> dict:
    """Main Hub entry point. Called by executor when hub_chat dispatched."""
    message = tool_input.get("message", "")
    user_info = tool_input.get("user", {})
    history = tool_input.get("history", [])
    skeleton = tool_input.get("skeleton", {})
    context = tool_input.get("context", {})

    pre_discovered = tool_input.get("_discovered", [])

    # ── Kernel Language Detection — LLM-only, persisted in Redis ──
    # Read last known language from Redis (set by previous LLM routing call)
    _user_id_for_lang = user_info.get("id", "")
    _cached_lang = ""
    try:
        _hr = await _get_hub_redis()
        _cached_lang = await _hr.get(f"imperal:user_lang:{_user_id_for_lang}") or ""
    except Exception:
        pass
    if _cached_lang:
        context["_user_language"] = _cached_lang
        context["_user_language_name"] = _LANG_NAMES.get(_cached_lang, _cached_lang.upper())

    # Extract allowed extensions for this user (pre-filtered by session_workflow access_policy)
    # Build allowed apps from skeleton context (pre-filtered by session_workflow access_policy)
    # None = backwards compat (no filter). set() = strict filter (even if empty = show nothing)
    _skel_ctx = skeleton.get("_context", {}) if isinstance(skeleton, dict) else {}
    _ext_info = _skel_ctx.get("extensions_info", [])
    if _ext_info:
        _user_allowed_apps = {_ei.get("app_id", "") for _ei in _ext_info}
        _user_allowed_apps.discard("")  # remove empty strings
    else:
        _user_allowed_apps = set()  # empty set = strict, show nothing

    # ── Capabilities query → always navigate (show ALL extensions) ──
    if _is_capabilities_query(message):
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)

    # ── KERNEL GUARD: Short ack/dismissal → ALWAYS navigate, NEVER dispatch ──
    # "Не", "ок", "спасибо" etc. must never trigger function calls.
    if _is_short_ack(message):
        log.info(f"Hub: short ack detected ('{message[:30]}') → navigate (no dispatch)")
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)


    # ── Step 1: DISCOVER (embeddings) ─────────────────────────────
    if pre_discovered:
        found_tools = pre_discovered
    elif catalog and catalog.loaded:
        user_scopes = user_info.get("scopes", ["*"])
        found_tools = await catalog.search(
            query=message,
            top_k=5,
            user_scopes=user_scopes,
        )
    else:
        found_tools = []

    # Group by unique app_id — keep best candidate per extension
    all_extensions = {}
    for t in found_tools:
        app_id = t.get("app_id", "")
        score = t.get("relevance", 0)
        if score >= 0.15 and (app_id not in all_extensions or score > all_extensions[app_id].get("relevance", 0)):
            all_extensions[app_id] = t

    # ── Embeddings as OPTIMIZATION, not GATE ─────────────────────
    # High score → FAST PATH (skip LLM, save ~200ms).
    # Low score → LLM routing decides (Haiku handles ANY language).
    # LLM returns "none" → navigate. Embeddings never block LLM.
    is_automation = bool(context.get("automation_rule_id"))
    _max_score = max((t.get("relevance", 0) for t in found_tools), default=0)

    is_multi = _is_multi_topic(message)
    intent_type = "read"  # default intent
    _used_fast_path = False

    # No fast path — ALWAYS route through Haiku for consistent:
    # 1. Routing (multilingual, context-aware)
    # 2. Intent classification (read/write/destructive)
    # 3. Language detection (authoritative, every message)
    # Cost: ~$0.0005/msg, ~150ms. Worth it for AI Cloud OS correctness.
    if False:  # fast path disabled
        pass

    # ── Automation intent detection (keyword-based, no LLM needed) ──
    if is_automation:
        _msg_lower = message.lower()
        _write_kw = ("send", "reply", "create", "forward", "compose", "save", "update",
                     "replace", "modify", "edit", "change", "move", "switch", "set", "put",
                     "отправь", "создай", "ответь", "перешли", "сохрани", "обнови",
                     "замени", "измени", "редактируй", "перемести", "установи")
        _destructive_kw = ("delete", "remove", "archive", "trash", "suspend",
                           "удали", "убери", "заархивируй")
        if any(w in _msg_lower for w in _destructive_kw):
            intent_type = "destructive"
        elif any(w in _msg_lower for w in _write_kw):
            intent_type = "write"
        log.info(f"Hub automation intent: {intent_type} for '{message[:60]}'")

    if not is_automation and catalog and catalog.loaded:
        llm_app_ids, intent_type, _llm_lang = await _route_with_llm(message, catalog, history, user_id=user_info.get("id", ""), allowed_apps=_user_allowed_apps)
        # LLM-detected language is authoritative (Haiku understands ALL languages)
        if _llm_lang and len(_llm_lang) == 2:
            context["_user_language"] = _llm_lang
            context["_user_language_name"] = _LANG_NAMES.get(_llm_lang, _llm_lang.upper())
            # Persist for future messages (ack/greetings skip LLM routing)
            try:
                _hr = await _get_hub_redis()
                await _hr.setex(f"imperal:user_lang:{user_info.get('id', '')}", 86400, _llm_lang)
            except Exception:
                pass
        if llm_app_ids:
            # LLM routing succeeded — use as PRIMARY, override embedding candidates
            llm_extensions = {}
            for app_id in llm_app_ids:
                if app_id in all_extensions:
                    llm_extensions[app_id] = all_extensions[app_id]
                    llm_extensions[app_id]["relevance"] = 0.9
                else:
                    for t in catalog.tools:
                        if t.get("app_id") == app_id:
                            llm_extensions[app_id] = {**t, "relevance": 0.9}
                            break
            if llm_extensions:
                all_extensions = llm_extensions
                log.info(f"Hub LLM routing PRIMARY: {list(all_extensions.keys())} (intent={intent_type})")
        else:
            # LLM routing returned "none" or empty
            # Before navigating: check if this could be a management follow-up
            # (e.g. "включи обратно" after admin suspended an extension)
            _mgmt_keywords = ("enable", "disable", "activate", "suspend", "включи", "выключи",
                              "верни", "обратно", "turn on", "turn off")
            _msg_lower = message.lower()
            _is_mgmt_followup = any(kw in _msg_lower for kw in _mgmt_keywords)
            
            if _is_mgmt_followup and ("admin" in _user_allowed_apps):
                # Route to admin as management fallback
                for t in catalog.tools:
                    if t.get("app_id") == "admin":
                        all_extensions = {"admin": {**t, "relevance": 0.9}}
                        intent_type = "write"
                        log.info(f"Hub: management fallback → admin (msg='{message[:50]}', max_emb_score={_max_score:.3f})")
                        break
                else:
                    log.info(f"Hub LLM routing: none → navigate (max_emb_score={_max_score:.3f})")
                    return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)
            else:
                log.info(f"Hub LLM routing: none → navigate (max_emb_score={_max_score:.3f})")
                return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)

    # Store intent_type in context for executor KAV verification
    context["_intent_type"] = intent_type

    # RBAC filter: remove extensions the user doesn't have access to (per access_policy)
    if _user_allowed_apps:
        all_extensions = {k: v for k, v in all_extensions.items() if k in _user_allowed_apps}

    # Select dispatch targets based on LLM routing result
    if is_automation and all_extensions:
        target = _detect_automation_target(message, all_extensions)
        if target and target in all_extensions:
            extensions = {target: all_extensions[target]}
        else:
            sorted_exts = sorted(all_extensions.items(), key=lambda x: x[1].get("relevance", 0), reverse=True)
            extensions = {sorted_exts[0][0]: sorted_exts[0][1]}
        log.info(f"Hub: automation action → {list(extensions.keys())} only")
    else:
        extensions = _select_dispatch_targets(all_extensions, message)

    log.info(f"Hub: message='{message[:60]}', discovered={len(found_tools)}, candidates={len(all_extensions)}, dispatching={list(extensions.keys())}, intent={intent_type}")

    # ── Kernel Context Enrichment — inject session state for follow-ups ──
    user_id = user_info.get("id", "")
    enriched_message = await _enrich_if_followup(message, user_id)

    # No matches even after LLM routing — session state fallback for follow-ups
    if not extensions:
        session_state = await _load_session_state(user_id)
        if session_state and session_state.get("last_app") and catalog and catalog.loaded:
            last_app = session_state["last_app"]
            # Try last_app first — but ONLY if user has access (RBAC check)
            if last_app in _user_allowed_apps:
                for t in catalog.tools:
                    if t.get("app_id") == last_app:
                        extensions = {last_app: {**t, "relevance": 0.8}}
                        log.info(f"Hub session fallback: -> last_app={last_app}")
                        break
            # last_app not accessible -> admin fallback (only if user has access)
            if not extensions:
                if "admin" in _user_allowed_apps:
                    for t in catalog.tools:
                        if t.get("app_id") == "admin":
                            extensions = {"admin": {**t, "relevance": 0.8}}
                            log.info(f"Hub session fallback: last_app={last_app} unavailable -> admin")
                            break

    if not extensions:
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)

    # Single extension — fast path with auto-reroute
    if len(extensions) == 1:
        app_id, candidate = next(iter(extensions.items()))
        # Hub ALWAYS waits for full result — no sub-extension promotion.
        # Outer hub_chat is already inline (300s timeout from session_workflow).
        context["_suppress_promotion"] = True
        result = await _dispatch_one(execute_fn, app_id, candidate["activity_name"],
                                     enriched_message, user_info, history, skeleton, context)
        # Passthrough: confirmation goes to session_workflow (task_promoted should NOT happen now)
        if _is_passthrough(result):
            context.pop("_suppress_promotion", None)
            log.info(f"Hub passthrough: {result.get('type')} from {app_id}")
            return result
        # Extract response text + truth flags from dispatch result
        _truth_flags = {}
        if isinstance(result, dict) and "response" in result:
            _truth_flags = {k: v for k, v in result.items() if k.startswith("_had_")}
            result_text = _strip_kernel_context(result.get("response", str(result)))
            log.info(f"Hub single dispatch result: app={app_id} _had_fn={result.get('_had_function_calls')} _had_action={result.get('_had_successful_action')} _handled={result.get('_handled')} truth_flags={_truth_flags}")
        elif isinstance(result, str):
            result_text = result
        else:
            result_text = str(result)

        # Check: extension didn't call any functions OR returned error
        _was_handled = True
        if isinstance(result, dict):
            _was_handled = result.get("_handled", True)

        if not _was_handled or _is_extension_error(result_text if isinstance(result_text, str) else str(result)):
            log.info(f"Hub: {app_id} not handled (_handled={_was_handled}), trying fallbacks")
            # Try other extensions from all_extensions
            for fallback_app, fallback_candidate in all_extensions.items():
                if fallback_app != app_id:
                    fb_result = await _dispatch_one(
                        execute_fn, fallback_app, fallback_candidate["activity_name"],
                        message, user_info, history, skeleton, context)
                    if _is_passthrough(fb_result):
                        return fb_result
                    fb_handled = True
                    fb_flags = {}
                    if isinstance(fb_result, dict):
                        fb_handled = fb_result.get("_handled", True)
                        fb_flags = {k: v for k, v in fb_result.items() if k.startswith("_had_")}
                        fb_text = fb_result.get("response", str(fb_result))
                    else:
                        fb_text = str(fb_result)
                    if fb_handled and not _is_extension_error(fb_text):
                        _fb_result = {"response": fb_text, **fb_flags}
                        if isinstance(fb_result, dict) and fb_result.get("_action_meta"):
                            _fb_result["_action_meta"] = fb_result["_action_meta"]
                        if isinstance(fb_result, dict) and fb_result.get("_functions_called"):
                            _fb_result["_functions_called"] = fb_result["_functions_called"]
                        if fb_flags.get("_had_function_calls"):
                            _fb_result["_message_type"] = "function_call"
                        return _fb_result
            # All fallbacks failed — navigate
            return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)
        context.pop("_suppress_promotion", None)
        await _save_session_state(user_id, app_id, result if isinstance(result, dict) else {"response": result_text})
        _result = {"response": result_text, **_truth_flags}
        if isinstance(result, dict) and result.get("_action_meta"):
            _result["_action_meta"] = result["_action_meta"]
        if isinstance(result, dict) and result.get("_functions_called"):
            _result["_functions_called"] = result["_functions_called"]
        # Set message type for delivery label
        if _truth_flags.get("_had_function_calls"):
            _result["_message_type"] = "function_call"
        return _result

    # ── Step 2: CHAIN EXECUTION ──────────────────────────────────
    # Single LLM call plans ordered steps with per-step messages.
    # Same extension CAN appear multiple times (e.g. gmail read → notes → gmail send).
    chain_steps = await _plan_chain_steps(enriched_message, list(extensions.keys()))
    _chain_fc = []  # Collect _functions_called from all chain steps
    _chain_meta = None  # Last step's _action_meta
    
    # Create persistent chain task for System Tray (NO task.promoted SSE — no chat card)
    _chain_task_id = None
    try:
        from imperal_sdk.runtime.task_manager import generate_task_id, create_task, update_progress, complete_task, promote_task
        _chain_redis = await _get_hub_redis()
        _chain_task_id = generate_task_id()
        await create_task(_chain_redis, _chain_task_id, user_id, "default",
                          "__system__", "chain", message[:200], threshold_ms=0)
        await promote_task(_chain_redis, _chain_task_id)  # visible=True for tray
        # Publish SSE for SystemMonitor real-time updates (ChatClient doesn't listen to scope 'task')
        try:
            await _chain_redis.publish("imperal:events:default", json.dumps({
                "type": "state_changed", "scope": "task", "action": "promoted",
                "data": {"task_id": _chain_task_id, "message_preview": message[:200],
                         "app_id": "__system__", "tool_name": "chain", "user_id": user_id}
            }))
        except Exception:
            pass
        log.info(f"Hub chain: tray task {_chain_task_id} for {len(chain_steps)} steps")
    except Exception as _ct_err:
        log.warning(f"Hub chain: tray task failed: {_ct_err}")

    successful = []  # list of (app_id, result_str) — preserves order + duplicates
    _truth_flags = {}
    
    _chain_total = len(chain_steps)
    for _chain_idx, (app_id, step_message) in enumerate(chain_steps):
        if app_id not in extensions:
            continue
        candidate = extensions[app_id]

        # Update status between chain steps so frontend knows we are alive
        _step_label = f"Step {_chain_idx + 1}/{_chain_total}: {step_message[:60]}..."
        await _update_chain_status(user_id, context, _step_label)
        if _chain_task_id:
            try:
                _pct = int((_chain_idx / _chain_total) * 100)
                await update_progress(_chain_redis, _chain_task_id, _pct, _step_label)
                await _chain_redis.publish("imperal:events:default", json.dumps({
                    "type": "state_changed", "scope": "task", "action": "progress",
                    "data": {"task_id": _chain_task_id, "percent": _pct,
                             "progress_message": _step_label, "user_id": user_id}
                }))
            except Exception:
                pass

        _chain_ctx = _build_chain_step_context(_chain_idx, successful)
        enriched_msg = f"{_chain_ctx}\n\n{step_message}" if _chain_ctx else step_message
        
        # Suppress task promotion in chain mode — we need all results for combine.
        # Chain mode: don't set _intent_type from keywords — they break non-EN/RU languages.
        # The function's @chat.function(action_type=...) is the source of truth.
        # ChatExtension reads action_type from the decorator, not from Hub intent.
        context["_intent_type"] = "chain"  # Special value: bypasses intent guard in extension
        context["_suppress_promotion"] = True
        context["_chain_mode"] = True
        result = await _dispatch_one(
            execute_fn, app_id, candidate["activity_name"],
            enriched_msg, user_info, history, skeleton, context,
        )
        context.pop("_suppress_promotion", None)
        context.pop("_chain_mode", None)
        
        # confirmation / task_limit_reached — must stop chain
        if _is_passthrough(result):
            log.info(f"Hub chain passthrough: {result.get('type')} from {app_id}")
            return result
        
        if isinstance(result, dict) and "response" in result:
            result_str = result["response"]
        else:
            result_str = str(result)
        if isinstance(result, Exception):
            log.info(f"Hub chain: {app_id} step {_chain_idx+1} raised exception, skipping")
            continue
        
        _chain_handled = True
        if isinstance(result, dict):
            _chain_handled = result.get("_handled", True)
        refused = not _chain_handled or _is_extension_error(result_str)
        if refused:
            log.info(f"Hub chain: {app_id} step {_chain_idx+1} refused, continuing")
            continue
        
        # Collect truth flags + verification data from chain steps
        if isinstance(result, dict) and result.get("_had_function_calls"):
            _truth_flags["_had_function_calls"] = True
        if isinstance(result, dict) and result.get("_had_successful_action"):
            _truth_flags["_had_successful_action"] = True
        if isinstance(result, dict) and result.get("_functions_called"):
            _chain_fc.extend(result["_functions_called"])
        if isinstance(result, dict) and result.get("_action_meta"):
            _chain_meta = result["_action_meta"]
        successful.append((app_id, result_str))
        log.info(f"Hub chain: {app_id} step {_chain_idx+1} done, passing context to next")
    
    if not successful:
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton)

    _last_app, _last_result = successful[-1]
    await _save_session_state(user_id, _last_app, {"response": _last_result})

    await _update_chain_status(user_id, context, "Combining results...")

    # __ Step 3: COMBINE ───────────────────────────────────────────
    # Convert list to dict for combine (merge duplicate app results)
    _combine_dict = {}
    for _s_idx, (_s_app, _s_result) in enumerate(successful):
        _key = f"{_s_app}" if _s_app not in _combine_dict else f"{_s_app} (step {_s_idx+1})"
        _combine_dict[_key] = _s_result
    combined = await _hub_combine(message, _combine_dict, user_info)
    combined.update(_truth_flags)
    if _chain_fc:
        combined["_functions_called"] = _chain_fc
    if _chain_meta:
        combined["_action_meta"] = _chain_meta

    # Complete chain tray task
    if _chain_task_id:
        try:
            await complete_task(_chain_redis, _chain_task_id, user_id, "completed")
            await _chain_redis.publish("imperal:events:default", json.dumps({
                "type": "state_changed", "scope": "task", "action": "completed",
                "data": {"task_id": _chain_task_id, "user_id": user_id}
            }))
        except Exception:
            pass
    # Set message type: function_call if any step called functions, else response
    if _truth_flags.get("_had_function_calls"):
        combined["_message_type"] = "function_call"
    return combined

async def _dispatch_one(execute_fn, app_id: str, tool_name: str, message: str,
                        user_info: dict, history: list, skeleton: dict,
                        context: dict) -> str | dict:
    """Dispatch to a single extension via kernel execute_sdk_tool.
    
    Returns:
        str: normal response text (no truth flags needed — navigate/error)
        dict: passthrough kernel signal OR response with truth flags
    """
    try:
        result = await execute_fn({
            "app_id": app_id,
            "tool_name": tool_name,
            "message": message,
            "user": user_info,
            "history": history,
            "skeleton": skeleton,
            "context": context,
        })
        if isinstance(result, dict):
            # Kernel signals pass through unchanged — session_workflow handles them
            if result.get("type") in _PASSTHROUGH_TYPES:
                return result
            # Always return dict with truth flags + _handled for chain refused detection
            response = result.get("response", str(result))
            _out = {
                "response": response,
                "_had_function_calls": result.get("_had_function_calls", False),
                "_had_successful_action": result.get("_had_successful_action", False),
                "_handled": result.get("_handled", True),
            }
            if result.get("_action_meta"):
                _out["_action_meta"] = result["_action_meta"]
            if result.get("_functions_called"):
                _out["_functions_called"] = result["_functions_called"]
            return _out

        return {"response": str(result), "_handled": False}
    except Exception as e:
        log.error(f"Hub dispatch error {app_id}/{tool_name}: {e}")
        return {"response": "An error occurred while processing your request.", "_handled": False}

async def _hub_navigate(message: str, history: list, user_info: dict, catalog, allowed_apps: set = None, context: dict = None, skeleton: dict = None) -> dict:
    """Navigation mode — conversational assistant when no extension matches."""
    capabilities = []
    user_scopes = user_info.get("scopes", ["*"])
    user_role = user_info.get("role", "user")
    _user_id = user_info.get("id", "")

    # Filter capabilities using allowed_extensions from skeleton context
    # This is already filtered by access_policy in load_all_user_extensions
    _allowed_apps = allowed_apps  # None = no filter, empty set = NO extensions visible

    if catalog and catalog.loaded:
        ext_tools = {}
        for t in catalog.tools:
            app_id = t.get("app_id", "")
            # Only show extensions the user has access to (pre-filtered by session_workflow)
            if _allowed_apps is not None and app_id not in _allowed_apps:
                continue
            app = t.get("app_display_name", t.get("app_id", "unknown"))
            desc = t.get("description", t.get("name", ""))
            ext_tools.setdefault(app, []).append(desc)
        for app_name, tools in ext_tools.items():
            tool_list = "; ".join(t for t in tools if t)
            capabilities.append(f"- **{app_name}**: {tool_list}" if tool_list else f"- **{app_name}**")
        # Show automations capability only if user has automations scope AND has extensions
        _has_auto = "*" in user_scopes or "automations:*" in user_scopes or "automations:read" in user_scopes
        if _has_auto:
            capabilities.append("- **Automations**: create, list, pause, resume, and delete automation rules")

    capabilities_text = "\n".join(capabilities) if capabilities else "No extensions installed."
    user_email = user_info.get("email", "unknown")
    user_role = user_info.get("role", "user")

    # ── Fresh time calculation (never stale) ──────────────────────
    _user_tz_str = "UTC"
    # Source 1: user_info attributes (most reliable)
    _ui_attrs = user_info.get("attributes", {})
    # Assistant name/avatar: Redis cache (set by admin via platform config)
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
    # Source 2: context._time (may have timezone even if time is stale)
    if _user_tz_str == "UTC" and context:
        _time_ctx = context.get("_time", {})
        if isinstance(_time_ctx, dict):
            _user_tz_str = _time_ctx.get("timezone") or _user_tz_str
        elif hasattr(_time_ctx, "timezone") and _time_ctx.timezone:
            _user_tz_str = _time_ctx.timezone
    # Source 3: skeleton user attributes
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
    # Build automations section conditionally (only if user has automations scope)
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
4. Respond in the user's language. No emojis. "Imperal" not "Imperial".
5. Be confident, concise, and proactive. Suggest what you can do. Offer next steps.
6. NEVER mention internal routing, extensions by name, or technical architecture.
7. When user says thanks/goodbye — respond briefly and warmly. No function calls needed.
8. When asked "what can you do?" — describe ONLY capabilities from YOUR CAPABILITIES section above. NEVER mention features not in your catalog.
9. Be PROACTIVE: if user shows interest in a topic, suggest related actions. "Показать письма? Хочешь чтобы я также проверил непрочитанные?"
10. For greetings: introduce yourself briefly, mention your key capabilities, and ask what the user needs. Include current time if relevant.
11. LANGUAGE: ALWAYS respond in the SAME language as the user's message. Russian message → Russian response. English → English. NEVER mix languages. This is non-negotiable.
12. NO EMOJIS. Never use emoji characters. Professional tone only.
13. CRITICAL: NEVER describe or suggest capabilities not listed in YOUR CAPABILITIES. If a user asks about a feature not in your catalog, say you cannot help with that. NEVER assume admin, cases, or other features exist unless they appear in YOUR CAPABILITIES."""

    messages = []
    for h in (history or [])[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        provider = _get_llm()
        resp = await provider.create_message(
            model=HUB_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        text = resp.content[0].text if resp.content else "Hello! How can I help you?"
        # Navigate = conversational mode. Only strip emojis, NOT filler phrases.
        import re as _re
        text = _re.sub(
            r'[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F'
            r'\u200D\u2702-\u27B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
            r'\u2B50\u26A0\u2B06\u2194-\u21AA]+', '', text
        )
        return {"response": text.strip()}
    except Exception as e:
        log.error(f"Hub navigate error: {e}")
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
            model=HUB_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": f"User asked: {message}\n\nExtension results:{results_text}"}],
        )
        text = resp.content[0].text if resp.content else next(iter(results.values()))
        return {"response": text}
    except Exception as e:
        log.error(f"Hub combine error: {e}")
        combined = "\n\n".join(f"**{app}:** {data}" for app, data in results.items())
        return {"response": combined}
