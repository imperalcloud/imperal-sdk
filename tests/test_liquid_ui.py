# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Tests for ICNLI Liquid Intent UI components in imperal_sdk.ui."""
from imperal_sdk import ui
from imperal_sdk.ui import (
    MorphingState,
    Affordance,
    CognitiveContext,
)


def test_affordance_to_dict():
    aff = Affordance(
        id="reboot",
        label="Reboot Server",
        description="Gracefully restart node",
        primary=True,
        risk="destructive",
        requires_confirmation=True,
        shortcut="Ctrl+R",
        payload={"node": "us-node1"},
    )
    d = aff.to_dict()
    assert d["id"] == "reboot"
    assert d["label"] == "Reboot Server"
    assert d["primary"] is True
    assert d["risk"] == "destructive"
    assert d["requires_confirmation"] is True
    assert d["shortcut"] == "Ctrl+R"
    assert d["payload"] == {"node": "us-node1"}


def test_cognitive_context_to_dict():
    cog = CognitiveContext(
        situation="incident_response",
        urgency="critical",
        attention_budget="glance",
        modality_hint="touch_mobile",
    )
    d = cog.to_dict()
    assert d["situation"] == "incident_response"
    assert d["urgency"] == "critical"
    assert d["attention_budget"] == "glance"
    assert d["modality_hint"] == "touch_mobile"


def test_morphing_state_serialization():
    aff1 = Affordance(id="isolate", label="Isolate Cluster", risk="destructive")
    aff2 = {"id": "ignore", "label": "Ignore Alert", "risk": "read"}
    cog = CognitiveContext(situation="outage", urgency="critical")

    state = MorphingState(
        context="split_brain_detector",
        summary="Cluster split brain detected",
        urgency="critical",
        risk="destructive",
        details="Replication lag > 60s between US and EU",
        affected_entities=["us-node1", "nl-node2"],
        metrics={"lag_ms": 61200, "unacked_tx": 42},
        affordances=[aff1, aff2],
        cognitive=cog,
    )

    d = state.to_dict()
    assert d["component"] == "MorphingState"
    assert d["context"] == "split_brain_detector"
    assert d["summary"] == "Cluster split brain detected"
    assert d["urgency"] == "critical"
    assert d["risk"] == "destructive"
    assert d["details"] == "Replication lag > 60s between US and EU"
    assert d["affected_entities"] == ["us-node1", "nl-node2"]
    assert d["metrics"]["lag_ms"] == 61200
    assert len(d["affordances"]) == 2
    assert d["affordances"][0]["id"] == "isolate"
    assert d["affordances"][1]["id"] == "ignore"
    assert d["cognitive"]["situation"] == "outage"


def test_surface_projections():
    state = MorphingState(
        context="backup_failed",
        summary="Nightly DB backup failed",
        urgency="elevated",
        risk="write",
        affected_entities=["db-primary"],
        affordances=[
            Affordance(id="retry", label="Retry Backup", primary=True, shortcut="r"),
            Affordance(id="notify", label="Alert On-Call", shortcut="a"),
        ],
    )

    # Telegram projection: compact action card with inline buttons
    tg = state.project_for_surface("telegram")
    assert tg["surface"] == "telegram"
    assert tg["format"] == "action_card"
    assert "Nightly DB backup failed" in tg["headline"]
    assert len(tg["buttons"]) == 2
    assert tg["buttons"][0]["id"] == "retry"

    # Terminal projection: TUI block with numbered shortcuts
    term = state.project_for_surface("terminal")
    assert term["surface"] == "terminal"
    assert term["format"] == "tui_block"
    assert len(term["shortcuts"]) == 2
    assert "[1] Retry Backup (r)" in term["shortcuts"][0]

    # Panel projection: full rich card
    panel = state.project_for_surface("panel")
    assert panel["surface"] == "panel"
    assert panel["format"] == "rich_intent_card"
    assert panel["full_state"]["component"] == "MorphingState"
