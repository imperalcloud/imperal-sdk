from imperal_sdk.runtime.canon import project_canon


def test_id_from_fallback_chain_first_present_wins():
    spec = {"id_from": ["rule_id", "id"]}
    assert project_canon(spec, {"rule_id": "r1", "id": "x"})["id"] == "r1"
    assert project_canon(spec, {"id": "x"})["id"] == "x"
    assert project_canon(spec, {})["id"] == ""
