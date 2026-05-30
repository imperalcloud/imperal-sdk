"""Self-test for the contract-guard checks: prove each layer flags its real
2026-05-30 bug class AND does not false-positive on the correct values."""
from imperal_sdk.devtools.contract_checks import (
    check_constant_depth, check_wire_payload, check_decorator_roles,
)

# ── (c) semantic depth — the MAX_DEPTH off-by-one ────────────────────────
_KERNEL_DEPTH = {"constants": {"hub_dispatch": {"max_depth": {"value": 3, "counts_root": False}}}}


def test_depth_correct_value_4_passes():
    # SDK stack INCLUDES root, value=4 -> 3 nested calls == kernel's 3. No finding.
    sdk = {"constants": {"max_call_depth": {"value": 4, "counts_root": True}}}
    assert check_constant_depth(sdk, _KERNEL_DEPTH) == []


def test_depth_buggy_value_3_flagged():
    # SDK value=3 root-inclusive -> only 2 nested calls != kernel 3. Must flag.
    sdk = {"constants": {"max_call_depth": {"value": 3, "counts_root": True}}}
    findings = check_constant_depth(sdk, _KERNEL_DEPTH)
    assert len(findings) == 1 and findings[0].layer == "semantic"


# ── (b) wire payload — the track_usage amount-vs-quantity drift ──────────
_ROUTE = "POST /v1/billing/internal/usage/track"
_WIRE_CONTRACT = {"request_models": {_ROUTE: {"fields": {
    "user_id": {"required": True}, "tenant_id": {"required": True},
    "meter": {"required": True}, "quantity": {"required": False},
    "extension_id": {"required": False}}}}}


def test_wire_buggy_amount_flagged():
    sent = {"meter", "amount", "user_id", "tenant_id"}   # the pre-fix payload
    findings = check_wire_payload(_ROUTE, sent, _WIRE_CONTRACT)
    assert any("amount" in f.detail for f in findings) and findings[0].layer == "wire"


def test_wire_fixed_quantity_passes():
    sent = {"meter", "quantity", "user_id", "tenant_id"}  # the fixed payload
    assert check_wire_payload(_ROUTE, sent, _WIRE_CONTRACT) == []


# ── (c) decorator roles — the effects "consumed vs advisory" lie ─────────
_DEC_CONTRACT = {"consumed_decorator_fields": ["action_type", "chain_callable", "data_model"]}


def test_decorator_advisory_effects_passes():
    assert check_decorator_roles({"effects": "advisory", "action_type": "consumed"}, _DEC_CONTRACT) == []


def test_decorator_effects_marked_consumed_flagged():
    findings = check_decorator_roles({"effects": "consumed"}, _DEC_CONTRACT)
    assert len(findings) == 1 and findings[0].layer == "decorator"
