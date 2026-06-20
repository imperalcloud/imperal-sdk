from __future__ import annotations

from typing import Any

from .template import resolve_value, MISSING


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def eval_conditional(spec: dict, ctx: dict) -> str | None:
    """Evaluate a conditional verb spec and return the next step id or None.

    Comparators (static, non-Turing): eq, neq, gt, lt, in, exists.
    field is resolved via resolve_value; gt/lt coerce to float via _num.
    """
    cond = spec["if"]
    actual = resolve_value(cond["field"], ctx)
    result = False
    if "eq" in cond:
        result = str(actual) == str(cond["eq"])
    elif "neq" in cond:
        result = str(actual) != str(cond["neq"])
    elif "gt" in cond:
        a, b = _num(actual), _num(cond["gt"])
        result = a is not None and b is not None and a > b
    elif "lt" in cond:
        a, b = _num(actual), _num(cond["lt"])
        result = a is not None and b is not None and a < b
    elif "in" in cond:
        result = cond["in"] in actual if isinstance(actual, (list, str, dict)) else False
    elif "exists" in cond:
        present = actual is not MISSING and actual not in ("", None)
        result = present if cond["exists"] else not present
    return spec.get("then") if result else spec.get("else")
