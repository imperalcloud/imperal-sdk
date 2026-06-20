from imperal_sdk.runtime.verbs import eval_conditional


def _ctx():
    return {"steps": {"s1": {"count": 3, "ids": ["a"]}}, "event": {}, "prev": {}}


def test_gt_true_routes_then():
    spec = {"if": {"field": "{{steps.s1.count}}", "gt": 0}, "then": "s3", "else": None}
    assert eval_conditional(spec, _ctx()) == "s3"


def test_gt_false_routes_else():
    spec = {"if": {"field": "{{steps.s1.count}}", "gt": 10}, "then": "s3", "else": "s9"}
    assert eval_conditional(spec, _ctx()) == "s9"


def test_eq_and_in_and_exists():
    assert eval_conditional({"if": {"field": "{{steps.s1.count}}", "eq": 3}, "then": "t"}, _ctx()) == "t"
    assert eval_conditional({"if": {"field": "{{steps.s1.ids}}", "in": "a"}, "then": "t"}, _ctx()) == "t"
    assert eval_conditional({"if": {"field": "{{steps.s1.count}}", "exists": True}, "then": "t"}, _ctx()) == "t"
