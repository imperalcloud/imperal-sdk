# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Tests for IRSkeleton model (E5) and generate_ir skeleton slot production."""
import pytest
from imperal_sdk.ir.skeleton import IRSkeleton
from imperal_sdk.ir.produce import generate_ir
from imperal_sdk.ir.validator import validate_ir_dict
from imperal_sdk import Extension
from imperal_sdk.chat.extension import ChatExtension


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------

def test_skeleton_slot_model():
    sk = IRSkeleton.model_validate({
        "section": "rules",
        "shape": {"total": "int", "active": "int"},
        "producer": {"kind": "code", "module": "skeleton", "entry": "skeleton_refresh_rules"},
        "alert": False,
        "ttl": 300,
    })
    assert sk.section == "rules"
    assert sk.producer.kind == "code"
    assert sk.producer.module == "skeleton"  # type: ignore[union-attr]
    assert sk.producer.entry == "skeleton_refresh_rules"  # type: ignore[union-attr]
    assert sk.alert is False
    assert sk.ttl == 300


def test_skeleton_slot_model_defaults():
    """shape/alert/ttl have sensible defaults."""
    sk = IRSkeleton.model_validate({
        "section": "credits",
        "producer": {"kind": "code", "module": "skeleton", "entry": "skeleton_refresh_credits"},
    })
    assert sk.shape == {}
    assert sk.alert is False
    assert sk.ttl == 300


def test_skeleton_slot_model_alert_true():
    sk = IRSkeleton.model_validate({
        "section": "monitors",
        "producer": {"kind": "code", "module": "skeleton", "entry": "skeleton_refresh_monitors"},
        "alert": True,
        "ttl": 60,
    })
    assert sk.alert is True
    assert sk.ttl == 60


def test_skeleton_slot_model_extra_fields_forbidden():
    with pytest.raises(Exception):
        IRSkeleton.model_validate({
            "section": "rules",
            "producer": {"kind": "code", "module": "skeleton", "entry": "skeleton_refresh_rules"},
            "unknown_field": "bad",
        })


# ---------------------------------------------------------------------------
# Produce-level tests: generate_ir must populate app.skeleton
# ---------------------------------------------------------------------------

def _ext_with_skeleton():
    """Build a minimal extension that declares one skeleton section."""
    ext = Extension(app_id="sktest", version="1.0.0", display_name="Skeleton Test")

    @ext.skeleton("rules", alert=True, ttl=120)
    async def refresh_rules(ctx) -> dict:  # pragma: no cover
        return {"response": {"total": 0, "active": 0}}

    return ext


def _ext_with_skeleton_and_chat():
    """Extension with both a skeleton section and a chat function."""
    ext = Extension(app_id="sktest2", version="1.0.0", display_name="Skeleton+Chat")
    chat = ChatExtension(ext, description="Test chat")

    @ext.skeleton("credits", alert=False, ttl=300)
    async def refresh_credits(ctx) -> dict:  # pragma: no cover
        return {"response": {"balance": 0}}

    @chat.function(name="get_credits", description="Get credits")
    async def get_credits(ctx, params):  # pragma: no cover
        return None

    return ext


def test_generate_ir_produces_skeleton_slot():
    ir = generate_ir(_ext_with_skeleton())
    assert "skeleton" in ir["app"]
    skeletons = ir["app"]["skeleton"]
    assert isinstance(skeletons, list)
    assert len(skeletons) == 1

    sk = skeletons[0]
    assert sk["section"] == "rules"
    assert sk["producer"]["kind"] == "code"
    assert sk["producer"]["module"] == "skeleton"
    assert sk["producer"]["entry"] == "skeleton_refresh_rules"
    # Meta read from _skeleton attribute on ToolDef
    assert sk["alert"] is True
    assert sk["ttl"] == 120


def test_generate_ir_skeleton_absent_when_no_skeleton_tools():
    """Extensions without skeleton tools must not emit the skeleton key."""
    ext = Extension(app_id="plain", version="1.0.0", display_name="Plain")
    ir = generate_ir(ext)
    assert ir["app"].get("skeleton") is None


def test_generate_ir_skeleton_validates():
    """Produced IR with skeleton slot must pass validate_ir_dict."""
    ir = generate_ir(_ext_with_skeleton())
    errors = validate_ir_dict(ir)
    assert errors == []


def test_generate_ir_skeleton_and_functions_coexist():
    ir = generate_ir(_ext_with_skeleton_and_chat())
    skeletons = ir["app"].get("skeleton", [])
    assert any(s["section"] == "credits" for s in skeletons)
    fns = ir["app"]["functions"]
    assert any(f["name"] == "get_credits" for f in fns)
    assert validate_ir_dict(ir) == []


def test_generate_ir_skeleton_default_meta_when_no_underscore_attr():
    """If _skeleton attr is missing (plain tool named skeleton_refresh_*), derive defaults."""
    ext = Extension(app_id="fallback", version="1.0.0", display_name="Fallback")

    # Register a bare tool (no @ext.skeleton decorator) with skeleton_refresh_ prefix
    @ext.tool("skeleton_refresh_bare", scopes=[])
    async def bare_refresh(ctx) -> dict:  # pragma: no cover
        return {"response": {}}

    ir = generate_ir(ext)
    skeletons = ir["app"].get("skeleton", [])
    assert len(skeletons) == 1
    sk = skeletons[0]
    assert sk["section"] == "bare"
    assert sk["alert"] is False
    assert sk["ttl"] == 300
