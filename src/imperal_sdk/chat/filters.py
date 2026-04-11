# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Output filtering pipeline for ChatExtension responses.

Enforces OS identity, response style, and tool result size limits.
All public functions are called by ChatExtension._handle() after each LLM turn.
"""
from __future__ import annotations
import json
import logging

log = logging.getLogger(__name__)


# ── OS Identity ───────────────────────────────────────────────────────────

_REDIRECT_PATTERNS = (
    "gmail extension", "notes extension", "admin extension",
    "sharelock extension", "mail extension", "case extension",
    "gmail app", "notes app", "another extension", "other extension",
    "separate extension", "different extension",
    "другое расширение", "другом расширении",
)


def enforce_os_identity(text: str) -> str:
    """Kernel-level OS identity enforcement.

    Removes any sentences that redirect user to other extensions.
    Extensions are internal implementation — user sees only Imperal Cloud.
    """
    if not text:
        return text

    text_lower = text.lower()
    has_redirect = any(p in text_lower for p in _REDIRECT_PATTERNS)
    if not has_redirect:
        return text

    # Remove redirect sentences
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    cleaned = []
    for s in sentences:
        s_lower = s.lower()
        if any(p in s_lower for p in _REDIRECT_PATTERNS):
            log.info(f"OS Identity: stripped redirect sentence: {s[:80]}")
            continue
        cleaned.append(s)

    result = " ".join(cleaned).strip()
    return result if result else text


# ── Response Style ────────────────────────────────────────────────────────

_FILLER_PHRASES = (
    "дайте знать", "let me know", "feel free to",
    "если вы хотите", "if you want to", "if you need",
    "ваши данные", "your data", "остаются сохранен",
    "в любой момент", "at any time", "anytime",
    "вы сможете снова", "you can re-enable", "you can always",
    "могу ещё чем-то помочь", "anything else",
    "что-то ещё", "чем-то помочь", "нужна ли", "нужно ли",
)


def enforce_response_style(text: str) -> str:
    """Kernel-level response style enforcement. CODE, not prompt.

    1. Strips Unicode emojis (no extension should use them)
    2. Strips known filler/reassurance phrases
    3. Collapses excessive whitespace
    """
    if not text:
        return text
    import re
    # 1. Strip emojis (Unicode emoji ranges, expanded to catch keycaps and misc)
    text = re.sub(
        r'[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F'
        r'\u200D\u2702-\u27B0\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF'
        r'\u2B50\u26A0\u2B06\u2194-\u21AA'
        r'\u20E3\u2139\u2328\u23CF\u23E9-\u23F3\u23F8-\u23FA'
        r'\U000E0020-\U000E007F\u200B-\u200F\u2028-\u202F'
        r'\u2066-\u2069\uFFFC\uFFFD]+', '', text
    )
    # Also strip keycap sequences: digit + U+FE0F + U+20E3 (e.g. 1️⃣)
    text = re.sub(r'[\d#*]\uFE0F?\u20E3', '', text)
    # 2. Strip known filler phrases (case-insensitive line removal)
    lines = text.split("\n")
    non_empty_lines = [line for line in lines if line.strip()]
    # Only strip filler if there are OTHER non-filler lines to keep.
    # Never strip ALL lines — that results in empty response.
    cleaned = []
    for line in lines:
        line_lower = line.strip().lower()
        if not line_lower:
            cleaned.append(line)
            continue
        if any(f in line_lower for f in _FILLER_PHRASES):
            # Check: would removing this leave us with zero content?
            remaining = [
                l for l in non_empty_lines
                if l.strip().lower() != line_lower
                and not any(f in l.strip().lower() for f in _FILLER_PHRASES)
            ]
            if remaining:
                log.info(f"Response style: stripped filler: {line.strip()[:80]}")
                continue
            # else: this is the only meaningful line, keep it
        cleaned.append(line)
    text = "\n".join(cleaned)
    # 3. Collapse excessive blank lines (max 1)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Tool Result Trimmer ───────────────────────────────────────────────────

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
    """Recursively truncate lists and long string fields. Private — used only by trim_tool_result."""
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


def trim_tool_result(content: str, max_tokens: int = 3000,
                     list_max: int = 5, str_max: int = 500) -> str:
    """Trim oversized tool result content to fit within token budget.

    Attempts to parse as JSON and truncate intelligently; falls back to
    hard character truncation for non-JSON content.
    """
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
