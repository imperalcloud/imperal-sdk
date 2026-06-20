from imperal_sdk.runtime.template import resolve_value, resolve_path, MISSING


def _ctx():
    return {"steps": {"s1": {"ids": ["a", "b"], "count": 2}}, "event": {"id": "e1"}, "prev": {}}


def test_whole_string_returns_raw_object():
    assert resolve_value("{{steps.s1.ids}}", _ctx()) == ["a", "b"]   # raw list, NOT "a,b"
    assert resolve_value("{{steps.s1.count}}", _ctx()) == 2          # raw int


def test_interpolated_string_returns_string():
    assert resolve_value("count={{steps.s1.count}}", _ctx()) == "count=2"


def test_missing_path_is_sentinel():
    assert resolve_path(_ctx(), "steps.s9.x") is MISSING


def test_nested_dict_and_list_resolved():
    out = resolve_value({"ids": "{{steps.s1.ids}}", "lit": 5}, _ctx())
    assert out == {"ids": ["a", "b"], "lit": 5}
