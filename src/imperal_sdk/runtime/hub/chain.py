# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Hub chain — chain planning + utilities for multi-step execution."""
from __future__ import annotations

import logging

from imperal_sdk.runtime.hub.router import _get_llm, _PASSTHROUGH_TYPES

log = logging.getLogger(__name__)


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


async def _plan_chain_steps(message: str, app_ids: list[str], user_id: str = "") -> list[tuple[str, str]]:
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
            max_tokens=300,
            purpose="routing",
            user_id=user_id,
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
    
    return [(aid, message) for aid in app_ids]


def _is_passthrough(result) -> bool:
    """Check if executor result is a kernel signal that must pass through Hub unchanged."""
    return isinstance(result, dict) and result.get("type") in _PASSTHROUGH_TYPES
