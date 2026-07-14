# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Ф2 — UI surface models inside the imperal.json contract.

Factored out of ``manifest_schema`` (which is already ≥300 lines) to keep
the god-file rule. Imported into ``manifest_schema.__all__`` as public API.

Public symbols
--------------
- ``UINode``  — serialized declarative UI node; validates ``Input.type``
                against the Ф1 single source ``INPUT_TYPES``.
- ``Panel``   — one entry in ``manifest['panels']``; validates ``slot``
                against ``ALLOWED_PANEL_SLOTS`` and propagates ``UINode``
                validation through the ``tree`` field.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# === UI surface (Ф2 — ui.* inside the contract) ==============================

# Single source of truth for the Input.type enum lives in the SDK UI
# package (Ф1). The manifest schema CONSUMES it — it must never re-declare
# the set, or a second source of truth would reappear (the exact divergence
# this whole effort removes). Imported lazily inside validators to avoid
# importing the ui package at manifest_schema import time.


class UINode(BaseModel):
    """A serialized declarative UI node (mirror of ``ui.base.UINode.to_dict()``).

    Validates only the facts the contract owns: an ``Input`` node's
    ``props['type']`` must be one of the SDK's ``INPUT_TYPES`` (federal
    Ф2 — UI finally lives inside the manifest the Registry can see).
    All other node types / props pass through (props is a free dict;
    the frontend renderer owns the rest).
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1)
    props: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _input_type_in_enum(self) -> "UINode":
        if self.type == "Input" and "type" in self.props:
            from imperal_sdk.ui.input_components import INPUT_TYPES  # lazy import

            v = self.props["type"]
            if v not in INPUT_TYPES:
                raise ValueError(
                    f"ui.Input props['type'] '{v}' must be one of "
                    f"{list(INPUT_TYPES)}"
                )
        return self


class Panel(BaseModel):
    """One entry in ``manifest['panels']`` (Ф2, additive).

    ``tree`` is the serialized UINode tree the panel renders. At build time
    it is present only for panels declaring a static tree; runtime-rendered
    panels emit ``{}`` (``maybe_publish_panels`` reads the live runtime node,
    not this metadata). When a tree IS present it is validated, so an
    ``Input`` with an illegal ``type`` is rejected at manifest validation.

    ``icon``/``refresh``/``center_overlay`` mirror the ``@ext.panel(...)``
    decorator kwargs of the same name — ``Extension.panel()`` always stores
    them on ``ext._panels[panel_id]`` (they have defaults, so they are
    present even when the caller doesn't pass them explicitly), and
    ``generate_manifest()`` re-emits the entire decorator metadata dict
    (fixed 2026-07-12 after automations' workshop panel silently lost
    ``center_overlay: true`` on rebuild). ``default_width``/``min_width``/
    ``max_width`` are the additional sidebar-sizing kwargs extensions pass
    via ``**kwargs`` (see imperal-ext-billing's left sidebar panel).
    ``extra="allow"`` keeps this model in sync with any further ad hoc
    kwargs a panel decorator forwards, instead of requiring a schema edit
    for every new one — panel metadata is intentionally open-ended.
    """

    model_config = ConfigDict(extra="allow")

    slot: str
    tree: Dict[str, Any] = Field(default_factory=dict)
    panel_id: Optional[str] = None
    title: Optional[str] = None
    icon: Optional[str] = None
    refresh: Optional[str] = None
    center_overlay: Optional[bool] = None
    default_width: Optional[int] = None
    min_width: Optional[int] = None
    max_width: Optional[int] = None

    @field_validator("slot")
    @classmethod
    def _slot_allowed(cls, v: str) -> str:
        from imperal_sdk.types.contributions import ALLOWED_PANEL_SLOTS  # lazy import

        if v not in ALLOWED_PANEL_SLOTS:
            raise ValueError(
                f"panel slot '{v}' must be one of "
                f"{sorted(ALLOWED_PANEL_SLOTS)}"
            )
        return v

    @model_validator(mode="after")
    def _validate_tree(self) -> "Panel":
        # A non-empty dict tree is validated through UINode so an
        # Input.type violation inside a panel is caught at manifest level.
        if self.tree:
            UINode.model_validate(self.tree)
        return self


__all__ = ["UINode", "Panel"]
