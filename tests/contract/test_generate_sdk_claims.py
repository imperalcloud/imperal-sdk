import imperal_sdk
from imperal_sdk.devtools.generate_sdk_claims import generate_claims
from imperal_sdk.devtools.contract_checks import _effective_nested_calls


def test_claims_carry_depth_semantics_and_roles():
    c = generate_claims()
    md = c["constants"]["max_call_depth"]
    # Assert EFFECTIVE behavior (the guard's own principle), NOT the raw value:
    # the SDK's depth cap must permit the kernel's 6 nested inter-extension calls (default).
    assert md["counts_root"] is True
    assert _effective_nested_calls(md["value"], md["counts_root"]) == 6
    assert c["decorator_roles"]["effects"] == "advisory"
    assert c["decorator_roles"]["action_type"] == "consumed"


def test_claims_carry_http_payloads():
    # Wire-layer cross-check input for the Phase 1b kernel guard: the field-set
    # the SDK billing client actually sends per route. Must name 'quantity'
    # (the corrected field), never the stale 'amount'.
    c = generate_claims()
    route = "POST /v1/billing/internal/usage/track"
    assert "http_payloads" in c
    assert route in c["http_payloads"]
    fields = set(c["http_payloads"][route])
    assert "quantity" in fields, "http_payloads must send 'quantity', not 'amount'"
    assert "amount" not in fields, "stale 'amount' field must not be in http_payloads"


def test_claims_carry_sdk_version():
    # The kernel-side guard reads this to detect deployed-vs-validated SDK drift.
    c = generate_claims()
    assert c["_sdk_version"] == imperal_sdk.__version__
