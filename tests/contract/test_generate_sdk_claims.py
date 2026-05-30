from imperal_sdk.devtools.generate_sdk_claims import generate_claims
from imperal_sdk.devtools.contract_checks import _effective_nested_calls


def test_claims_carry_depth_semantics_and_roles():
    c = generate_claims()
    md = c["constants"]["max_call_depth"]
    # Assert EFFECTIVE behavior (the guard's own principle), NOT the raw value:
    # the SDK's depth cap must permit the kernel's 3 nested inter-extension calls.
    assert md["counts_root"] is True
    assert _effective_nested_calls(md["value"], md["counts_root"]) == 3
    assert c["decorator_roles"]["effects"] == "advisory"
    assert c["decorator_roles"]["action_type"] == "consumed"
