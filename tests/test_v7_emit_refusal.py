"""Test emit_refusal wiring in SDK chat handler."""


def test_emit_refusal_tool_schema_shape():
    from imperal_sdk.chat.refusal import EMIT_REFUSAL_TOOL
    assert EMIT_REFUSAL_TOOL["name"] == "emit_refusal"
    sch = EMIT_REFUSAL_TOOL["input_schema"]
    assert sch["required"] == ["reason", "user_message"]
    assert "no_scope" in sch["properties"]["reason"]["enum"]


def test_parse_refusal_roundtrip():
    from imperal_sdk.chat.refusal import parse_refusal_tool_use, RefusalEmission
    inp = {"reason": "missing_params", "user_message": "need email", "next_steps": ["provide email"]}
    r = parse_refusal_tool_use(inp)
    assert isinstance(r, RefusalEmission)
    assert r.reason == "missing_params"
    assert r.next_steps == ("provide email",)
    assert r.needs_human == {"what": "need email", "kind": "fact"}


def test_refusal_needs_human_mapping():
    from imperal_sdk.chat.refusal import RefusalEmission, REFUSAL_REASON_NEEDS_HUMAN
    assert REFUSAL_REASON_NEEDS_HUMAN == {
        "no_scope": "means",
        "missing_params": "fact",
    }
    assert RefusalEmission(reason="no_scope", user_message="Grant mail.send").needs_human == {
        "what": "Grant mail.send",
        "kind": "means",
    }
    assert RefusalEmission(reason="no_scope", user_message="  ").needs_human == {
        "what": "Required permission or scope is missing",
        "kind": "means",
    }
    assert RefusalEmission(reason="missing_params", user_message="").needs_human == {
        "what": "Required parameters must be provided",
        "kind": "fact",
    }
    for non_human in ("already_done", "tool_unavailable", "external_error"):
        assert RefusalEmission(reason=non_human, user_message="msg").needs_human is None


def test_refusal_needs_human_cuts_long_multiline_message():
    from imperal_sdk.chat.error_codes import NEEDS_HUMAN_WHAT_LIMIT
    from imperal_sdk.chat.refusal import RefusalEmission

    lines = [f"step-{i:02d}: missing parameter explanation from extension" for i in range(25)]
    msg = "\n".join(lines)
    assert len(msg) > NEEDS_HUMAN_WHAT_LIMIT
    nh = RefusalEmission(reason="missing_params", user_message=msg).needs_human
    assert nh is not None
    assert nh["kind"] == "fact"
    assert len(nh["what"]) <= NEEDS_HUMAN_WHAT_LIMIT
    assert "not shown here" in nh["what"]
    assert lines[0] in nh["what"]
    assert lines[-1] in nh["what"]
