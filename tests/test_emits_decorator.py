"""Tests for @ext.emits decorator and EmitsDef dataclass."""
import pytest
from imperal_sdk import Extension


def test_emits_decorator_registers():
    ext = Extension(app_id="billing", version="1.0.0")

    @ext.emits("billing.topup_completed", schema_ref="#/schemas/topup_completed")
    async def credit_wallet(ctx, amount: int):
        return {"ok": True}

    assert len(ext.declared_emits) == 1
    decl = ext.declared_emits[0]
    assert decl.event_type == "billing.topup_completed"
    assert decl.schema_ref == "#/schemas/topup_completed"


def test_emits_to_manifest():
    ext = Extension(app_id="billing", version="1.0.0")

    @ext.emits("billing.topup_completed", schema_ref="#/schemas/topup_completed")
    async def credit(ctx):
        return None

    manifest_dict = ext.declared_emits[0].to_manifest()
    assert manifest_dict == {
        "type": "billing.topup_completed",
        "schema_ref": "#/schemas/topup_completed",
    }


def test_emits_rejects_cross_namespace():
    ext = Extension(app_id="billing", version="1.0.0")
    with pytest.raises(ValueError, match="cross-namespace"):
        @ext.emits("notes.something")
        async def f(ctx):
            pass


def test_emits_rejects_undotted():
    """Undotted event_type fails — guards live for federal discipline."""
    ext = Extension(app_id="billing", version="1.0.0")
    with pytest.raises(ValueError, match="must be dotted"):
        @ext.emits("billingevent")
        async def f(ctx):
            pass


def test_emits_to_manifest_without_schema_ref():
    """When schema_ref is omitted (None), it should NOT appear in manifest dict."""
    ext = Extension(app_id="billing", version="1.0.0")

    @ext.emits("billing.simple_event")
    async def emit(ctx):
        return None

    manifest_dict = ext.declared_emits[0].to_manifest()
    assert manifest_dict == {"type": "billing.simple_event"}
    assert "schema_ref" not in manifest_dict


def test_declared_emits_property_returns_list():
    """Public declared_emits property exposes the list."""
    ext = Extension(app_id="billing", version="1.0.0")

    @ext.emits("billing.x")
    async def f(ctx): pass

    @ext.emits("billing.y")
    async def g(ctx): pass

    emits_list = ext.declared_emits
    assert isinstance(emits_list, list)
    assert len(emits_list) == 2
