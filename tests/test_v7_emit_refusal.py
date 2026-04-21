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
