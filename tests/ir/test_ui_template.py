from imperal_sdk.ir.ui_template import resolve_ui_tree


def test_binding_substitution_in_props():
    tree = {"type": "Card", "props": {"title": "Hi {{event.who}}"}}
    out = resolve_ui_tree(tree, {"event": {"who": "Val"}, "steps": {}, "prev": {}})
    assert out["props"]["title"] == "Hi Val"


def test_repeat_expands_list():
    tree = {"type": "Stack", "props": {"children": {
        "$repeat": "{{steps.s1.docs}}", "as": "row",
        "node": {"type": "Text", "props": {"value": "{{row.name}}"}}}}}
    ctx = {"steps": {"s1": {"docs": [{"name": "A"}, {"name": "B"}]}}, "event": {}, "prev": {}}
    out = resolve_ui_tree(tree, ctx)
    kids = out["props"]["children"]
    assert [k["props"]["value"] for k in kids] == ["A", "B"]


def test_if_keep():
    tree = {
        "$if": {"left": "{{event.ok}}", "op": "eq", "right": True},
        "node": {"type": "Banner", "props": {"text": "visible"}},
    }
    out = resolve_ui_tree(tree, {"event": {"ok": True}, "steps": {}, "prev": {}})
    assert out["type"] == "Banner"
    assert out["props"]["text"] == "visible"


def test_if_drop():
    tree = {
        "$if": {"left": "{{event.ok}}", "op": "eq", "right": True},
        "node": {"type": "Banner", "props": {"text": "hidden"}},
    }
    out = resolve_ui_tree(tree, {"event": {"ok": False}, "steps": {}, "prev": {}})
    assert out == {}
