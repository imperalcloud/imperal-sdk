"""Tests for @ext.emits decorator and EmitsDef dataclass."""
import pytest
from imperal_sdk import Extension


def test_emits_decorator_registers():
    ext = Extension(app_id="billing", version="1.0.0")

    @ext.emits("billing.topup_completed", schema_ref="#/schemas/topup_completed")
    async def credit_wallet(ctx, amount: int):
        return {"ok": True}

    assert len(ext._declared_emits) == 1
    decl = ext._declared_emits[0]
    assert decl.event_type == "billing.topup_completed"
    assert decl.schema_ref == "#/schemas/topup_completed"


def test_emits_to_manifest():
    ext = Extension(app_id="billing", version="1.0.0")

    @ext.emits("billing.topup_completed", schema_ref="#/schemas/topup_completed")
    async def credit(ctx):
        return None

    manifest_dict = ext._declared_emits[0].to_manifest()
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
