from imperal_sdk.devtools.generate_sdk_claims import generate_claims


def test_claims_carry_depth_semantics_and_roles():
    c = generate_claims()
    md = c["constants"]["max_call_depth"]
    assert md["value"] == 4 and md["counts_root"] is True   # current corrected SDK
    assert c["decorator_roles"]["effects"] == "advisory"
    assert c["decorator_roles"]["action_type"] == "consumed"
