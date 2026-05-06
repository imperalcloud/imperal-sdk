# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Pydantic feedback loop retry utilities — extracted from chat/handler.py
in v4.1.3 (2026-05-06) per CLAUDE.md rule 6 (>300 LOC files).

Public symbols re-exported from imperal_sdk.chat.handler for back-compat:
- format_pydantic_for_llm
- _emit_retry_outcome
- _RETRY_BUDGET
- _validation_missing_field_response

Federal: no behavioral change vs v4.1.2 — pure structural refactor.
Pydantic feedback loop semantics (SPEC2-LLM-ARGS-QUALITY, v4.1.0) and
invariants I-PYDANTIC-RETRY-BUDGET / SCOPE / FEEDBACK-STRUCTURED /
FC-SINGLE-APPEND / WIRE-FROZEN unchanged.
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError

from imperal_sdk.chat.filters import trim_tool_result

if TYPE_CHECKING:
    from imperal_sdk.chat.extension import ChatExtension

# Logger name pinned to "imperal_sdk.chat.handler" (NOT __name__) for two
# federal reasons:
#   1) SigNoz log scrape pipeline filters validation_retry_outcome lines by
#      logger name — emitting from imperal_sdk.chat.retry would silently
#      break production observability without a pipeline update.
#   2) Test contracts (tests/test_chat_pydantic_retry.py) capture logs at
#      logger="imperal_sdk.chat.handler" — same pin keeps them green.
# This is the wire-frozen invariant for retry-outcome logs (I-PYDANTIC-WIRE-FROZEN).
log = logging.getLogger("imperal_sdk.chat.handler")


# Pydantic validation retry budget per @chat.function call.
# Spec invariant I-PYDANTIC-RETRY-BUDGET (SPEC2-LLM-ARGS-QUALITY, v4.1.0).
_RETRY_BUDGET = 2


# ---------------------------------------------------------------------------
# Pydantic feedback loop helper (SPEC2-LLM-ARGS-QUALITY, v4.1.0)
# ---------------------------------------------------------------------------

def format_pydantic_for_llm(e: PydanticValidationError) -> str:
    """Convert PydanticValidationError to LLM-friendly retry feedback prose.

    Returns a multi-line string structured as:

        Your previous tool call had invalid arguments. Fix these issues:
        - '<loc>': <human reason>
        - '<loc>': <human reason>

        Retry the tool call with corrected arguments.

    Per-error-type templates (per spec section 6.1):
      missing            -> required field is missing — provide a value
      string_*           -> expected string, got {input_type}
      int_*              -> expected integer, got {input!r}
      datetime_*         -> expected ISO datetime (e.g. '2026-05-03T00:00:00'), got {input!r}
      list_type          -> expected list/array, got {input_type}
      extra_forbidden    -> unknown field — remove it
      (other)            -> loc: msg (Pydantic's own message)
    """
    lines = ["Your previous tool call had invalid arguments. Fix these issues:"]
    for err in e.errors():
        loc_parts = err.get("loc") or ()
        loc = ".".join(str(p) for p in loc_parts) if loc_parts else "<root>"
        err_type = err.get("type", "")
        msg = err.get("msg", "")
        input_val = err.get("input")
        input_type_name = type(input_val).__name__ if input_val is not None else "None"

        if err_type == "missing":
            lines.append(f"- '{loc}': required field is missing — provide a value")
        elif err_type.startswith("string_"):
            lines.append(f"- '{loc}': expected string, got {input_type_name}")
        elif err_type.startswith("int_"):
            lines.append(f"- '{loc}': expected integer, got {input_val!r}")
        elif err_type.startswith("datetime_"):
            lines.append(f"- '{loc}': expected ISO datetime (e.g. '2026-05-03T00:00:00'), got {input_val!r}")
        elif err_type == "list_type":
            lines.append(f"- '{loc}': expected list/array, got {input_type_name}")
        elif err_type == "extra_forbidden":
            lines.append(f"- '{loc}': unknown field — remove it")
        else:
            lines.append(f"- '{loc}': {msg}")
    lines.append("")
    lines.append("Retry the tool call with corrected arguments.")
    return "\n".join(lines)


# Outcome levels — per spec section 9 logging contract
_RETRY_OUTCOME_LEVELS: dict[str, int] = {
    "no_retry": logging.DEBUG,
    "success": logging.INFO,
    "redundant": logging.WARNING,
    "exhausted": logging.WARNING,
    "llm_gave_up": logging.INFO,
    "fabricated_id_on_retry": logging.WARNING,
}


def _emit_retry_outcome(*, tool: str, ext: str, outcome: str, retry_count: int) -> None:
    """Emit structured log line for SigNoz retry-outcome metrics derivation.

    Format (consumed by kernel log scrape -> SigNoz):
      validation_retry_outcome tool=<name> ext=<name> outcome=<value> retry_count=<N>

    Outcome enum (spec section 10): no_retry | success | exhausted | llm_gave_up |
    redundant | fabricated_id_on_retry.

    No OpenTelemetry dependency — counters derived from log lines via
    SigNoz log -> metric pipeline (same pattern kernel uses elsewhere).
    """
    level = _RETRY_OUTCOME_LEVELS.get(outcome, logging.INFO)
    log.log(
        level,
        "validation_retry_outcome tool=%s ext=%s outcome=%s retry_count=%d",
        tool, ext, outcome, retry_count,
    )


def _validation_missing_field_response(
    *,
    e: PydanticValidationError,
    chat_ext: "ChatExtension",
    tu,
    action_type: str,
    cfg: dict,
) -> str:
    """Build VALIDATION_MISSING_FIELD response, append fc, return trimmed content.

    Shared between exhausted-retry and llm-gave-up branches. Single fc-append
    per logical tool call (I-PYDANTIC-FC-SINGLE-APPEND).
    """
    missing: list = []
    for err in e.errors():
        if err.get("type") == "missing":
            loc_p = err.get("loc") or ()
            if loc_p:
                missing.append(loc_p[0])
    log.error(
        f"ChatExtension validation error {tu.name}: missing={missing}"
    )
    content = json.dumps({
        "RESULT": "ERROR",
        "error_code": "VALIDATION_MISSING_FIELD",
        "missing_fields": missing,
    })
    chat_ext._functions_called.append({
        "name": tu.name, "params": tu.input,
        "action_type": action_type, "success": False,
        "intercepted": False, "event": "",
        "result": {
            "error_code": "VALIDATION_MISSING_FIELD",
            "missing_fields": missing,
        },
    })
    return trim_tool_result(
        content, cfg["max_result_tokens"],
        cfg["list_truncate_items"], cfg["string_truncate_chars"],
    )
