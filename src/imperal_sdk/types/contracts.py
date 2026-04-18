# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""JSON Schema contracts for cross-boundary payloads.

Every payload that leaves a single Python process — across Temporal
activities, Redis pub/sub streams, SSE, or the Fast-RPC transport — is
covered here. Inside a process, the dataclass forms in `types/` remain
the ergonomic API; at the boundary, these Pydantic mirrors are the
machine-enforceable contract.

Covered (as of v1.5.10)
-----------------------
- `ActionResult`  — every `@chat.function` return value. Serialized by
  `ActionResult.to_dict()`, consumed by the kernel executor, Temporal
  history, automation template resolver, and SSE delivery.
- `Event`         — Redis-streams event envelope published by extensions
  (`@chat.function(event=...)`) and consumed by the automation engine,
  kernel SSE, and Panel live-refresh. Previously only documented as 10
  textual invariants (RPC-I1..I10) with no runtime schema.

Public API
----------
- `ActionResultModel`, `EventModel`          — Pydantic mirrors
- `validate_action_result_dict(data)`        — -> list[ValidationIssue]
- `validate_event_dict(data)`                -> list[ValidationIssue]
- `get_action_result_schema()`, `ACTION_RESULT_SCHEMA`
- `get_event_schema()`,         `EVENT_SCHEMA`

Rule codes (mirrors manifest_schema M1..M5 shape):
  `AR1..AR5`  — ActionResult payload issues
  `EV1..EV5`  — Event envelope issues

External tooling should prefer the committed static files at
`imperal_sdk/schemas/action_result.schema.json` and `event.schema.json`.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


# === Regex contracts =================================================

# Event type: "ns.action", "ns:action", "ns.sub.action", "ns:sub:action".
# Matches both dot-form (legacy, e.g. "sharelock.case_created") and
# colon-form (post session-28, e.g. "notes:created"). At least one
# namespace + action segment required.
EVENT_TYPE_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:[.:][a-z0-9_]+)+$"
)

# Imperal canonical user/tenant ID prefixes; `""` also allowed (system).
_IMP_USER_PATTERN = re.compile(r"^(imp_u_[A-Za-z0-9_]+|__system__|)$")
_IMP_TENANT_PATTERN = re.compile(r"^(imp_t_[A-Za-z0-9_]+|default|)$")


# === ActionResult mirror =============================================

class ActionResultModel(BaseModel):
    """Pydantic contract for `ActionResult.to_dict()` output.

    Mirrors the dataclass in `imperal_sdk.types.action_result` —
    the dataclass is the ergonomic API, this is the machine-enforceable
    boundary contract.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "error"]
    summary: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    retryable: bool = False
    ui: Optional[Dict[str, Any]] = None
    refresh_panels: Optional[List[str]] = None

    @model_validator(mode="after")
    def _status_error_consistency(self) -> "ActionResultModel":
        """status='error' requires non-empty error message.

        Invariant kept symmetric with `ActionResult.error()` factory —
        a malformed dict with status='error' and no error= is a hard
        contract violation (kernel has no user-facing message to show).
        """
        if self.status == "error" and not (self.error or "").strip():
            raise ValueError(
                "status='error' requires a non-empty 'error' field "
                "(factory: ActionResult.error(message))"
            )
        if self.status == "success" and self.error is not None:
            raise ValueError(
                "status='success' must not carry an 'error' field "
                "(factory: ActionResult.success(...))"
            )
        return self


# === Event mirror ====================================================

class EventModel(BaseModel):
    """Pydantic contract for platform Event envelopes on Redis streams.

    Mirrors the dataclass in `imperal_sdk.types.events.Event` — same
    five fields, strict validation.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: str
    timestamp: str = ""
    user_id: str = ""
    tenant_id: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _event_type_shape(cls, v: str) -> str:
        if not v or not EVENT_TYPE_PATTERN.match(v):
            raise ValueError(
                f"event_type '{v}' must be 'namespace.action' or "
                f"'namespace:action' (lowercase, underscore allowed in "
                f"segments; at least one separator)"
            )
        return v

    @field_validator("user_id")
    @classmethod
    def _user_id_shape(cls, v: str) -> str:
        if v and not _IMP_USER_PATTERN.match(v):
            raise ValueError(
                f"user_id '{v}' must be 'imp_u_*', '__system__', or empty"
            )
        return v

    @field_validator("tenant_id")
    @classmethod
    def _tenant_id_shape(cls, v: str) -> str:
        if v and not _IMP_TENANT_PATTERN.match(v):
            raise ValueError(
                f"tenant_id '{v}' must be 'imp_t_*', 'default', or empty"
            )
        return v


# === Shared validator plumbing =======================================

def _validate_against_model(
    data: Any,
    model: type,
    rule_prefix: str,
) -> List["ValidationIssue"]:
    """Run a dict through a Pydantic model, return ValidationIssue list.

    Rule-code scheme (mirrors manifest_schema):
      `{prefix}1`  root is not a JSON object
      `{prefix}2`  required field missing
      `{prefix}3`  unknown top-level field (typo detection)
      `{prefix}4`  invalid value (regex / type / enum / cross-field)
      `{prefix}5`  nested-field error (currently unused — both models
                   are flat — reserved for forward compat)
    """
    from imperal_sdk.validator import ValidationIssue

    issues: List[ValidationIssue] = []

    if not isinstance(data, dict):
        issues.append(ValidationIssue(
            rule=f"{rule_prefix}1", level="ERROR",
            message=(
                f"payload root must be a JSON object, "
                f"got {type(data).__name__}"
            ),
            fix=f"Ensure the {model.__name__} payload is a top-level {{...}} object",
        ))
        return issues

    try:
        model.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            etype = err["type"]
            msg = err["msg"]

            if etype == "missing":
                rule, fix = f"{rule_prefix}2", f"Add '{loc}' to the payload"
            elif etype == "extra_forbidden":
                rule, fix = f"{rule_prefix}3", (
                    f"Remove '{loc}' — not part of the {model.__name__} contract. "
                    f"Check for typos."
                )
            elif "." in loc:
                rule, fix = f"{rule_prefix}5", f"Fix nested value at '{loc}': {msg}"
            else:
                rule, fix = f"{rule_prefix}4", f"Fix value at '{loc}': {msg}"

            issues.append(ValidationIssue(
                rule=rule, level="ERROR",
                message=f"[{loc or 'root'}] {msg}",
                fix=fix,
            ))

    return issues


# === Public validators ===============================================

def validate_action_result_dict(data: Any) -> List["ValidationIssue"]:
    """Validate a dict against the `ActionResult.to_dict()` contract.

    Non-raising. Returns a list of ValidationIssue entries with rule
    codes `AR1..AR5`. Empty list means the payload conforms.
    """
    return _validate_against_model(data, ActionResultModel, "AR")


def validate_event_dict(data: Any) -> List["ValidationIssue"]:
    """Validate a dict against the platform Event envelope contract.

    Non-raising. Returns a list of ValidationIssue entries with rule
    codes `EV1..EV5`. Empty list means the envelope conforms.
    """
    return _validate_against_model(data, EventModel, "EV")


# === JSON Schema exports =============================================

def _shape_schema(schema: Dict[str, Any], *, id_slug: str, title: str, description: str) -> Dict[str, Any]:
    schema["$id"] = f"https://imperal.io/schemas/{id_slug}.schema.json"
    schema["title"] = title
    schema["description"] = description
    return schema


def get_action_result_schema() -> Dict[str, Any]:
    """JSON Schema (Draft 2020-12) for `ActionResult.to_dict()`."""
    return _shape_schema(
        ActionResultModel.model_json_schema(),
        id_slug="action_result",
        title="Imperal ActionResult Payload",
        description=(
            "Canonical return-value contract for every @chat.function. "
            "Produced by `ActionResult.to_dict()`; consumed by the "
            "Imperal kernel executor, Temporal activity history, "
            "automation template resolver, and SSE delivery."
        ),
    )


def get_event_schema() -> Dict[str, Any]:
    """JSON Schema (Draft 2020-12) for platform Event envelopes."""
    return _shape_schema(
        EventModel.model_json_schema(),
        id_slug="event",
        title="Imperal Platform Event Envelope",
        description=(
            "Canonical shape of Event payloads published on Redis "
            "streams and consumed by the automation engine, SSE "
            "delivery, and Panel live-refresh. Replaces the textual "
            "RPC-I1..I10 invariants with a machine-checkable contract."
        ),
    )


ACTION_RESULT_SCHEMA: Dict[str, Any] = get_action_result_schema()
EVENT_SCHEMA: Dict[str, Any] = get_event_schema()


__all__ = [
    "ActionResultModel",
    "EventModel",
    "validate_action_result_dict",
    "validate_event_dict",
    "get_action_result_schema",
    "get_event_schema",
    "ACTION_RESULT_SCHEMA",
    "EVENT_SCHEMA",
    "EVENT_TYPE_PATTERN",
]
