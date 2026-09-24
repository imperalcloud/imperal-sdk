# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Tests for ctx.surface dynamic situational awareness."""
import pytest
from imperal_sdk.context import Context, UserContext
from imperal_sdk.ui.liquid import MorphingState, Affordance
from imperal_sdk.types.action_result import ActionResult


def test_ctx_surface_defaults_to_panel():
    user = UserContext(imperal_id="imp_u_123", email="user@imperal.io", tenant_id="default", role="user")
    ctx = Context(user=user)
    assert ctx.surface == "panel"


def test_ctx_surface_from_metadata():
    user = UserContext(imperal_id="imp_u_123", email="user@imperal.io", tenant_id="default", role="user")
    ctx = Context(user=user, _metadata={"surface": "terminal"})
    assert ctx.surface == "terminal"

    ctx_tg = Context(user=user, _metadata={"caller_surface": "telegram"})
    assert ctx_tg.surface == "telegram"


def test_on_the_fly_morphing_adaptation():
    user = UserContext(imperal_id="imp_u_123", email="user@imperal.io", tenant_id="default", role="user")
    ctx = Context(user=user, _metadata={"surface": "telegram"})

    # Extension adapts on the fly to situation
    state = MorphingState(
        context="high_memory_usage",
        summary="Memory usage exceeded 90%",
        urgency="critical",
        risk="destructive",
        affordances=[
            Affordance(id="restart_service", label="Restart Service", risk="destructive", primary=True),
            Affordance(id="dismiss", label="Dismiss Alert", risk="read"),
        ],
    )

    action_res = ActionResult.morph(state)
    assert action_res.status == "success"
    assert action_res.ui is not None

    # Project on the fly based on active surface
    projection = state.project_for_surface(ctx.surface)
    assert projection["surface"] == "telegram"
    assert projection["format"] == "action_card"
    assert "Memory usage exceeded 90%" in projection["headline"]
    assert len(projection["buttons"]) == 2
