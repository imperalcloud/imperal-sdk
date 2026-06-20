from __future__ import annotations

from typing import Any

from ..runtime.template import resolve_value


def _eval_if(cond: dict, ctx: dict) -> bool:
    """Evaluate a {left, op, right} condition against ctx.

    Supports ops: eq, neq, gt, lt, in, exists.
    left is resolved via resolve_value; right is literal.
    Falls back to eval_conditional for {field, eq/neq/...} format.
    """
    if "field" in cond or ("left" not in cond and "op" not in cond):
        # delegate to eval_conditional's native format
        from ..runtime.verbs import eval_conditional
        return eval_conditional({"if": cond, "then": "y", "else": None}, ctx) == "y"

    actual = resolve_value(cond["left"], ctx)
    op = cond.get("op", "eq")
    right = cond.get("right")

    if op == "eq":
        return actual == right
    if op == "neq":
        return actual != right
    if op == "gt":
        try:
            return float(actual) > float(right)
        except (TypeError, ValueError):
            return False
    if op == "lt":
        try:
            return float(actual) < float(right)
        except (TypeError, ValueError):
            return False
    if op == "in":
        return right in actual if isinstance(actual, (list, str, dict)) else False
    if op == "exists":
        from ..runtime.template import MISSING
        present = actual is not MISSING and actual not in ("", None)
        return bool(right) == present
    return False


def _resolve_props(props: dict, ctx: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, dict) and "$repeat" in v:
            items = resolve_value(v["$repeat"], ctx)
            alias = v.get("as", "item")
            node = v["node"]
            out[k] = [
                resolve_ui_tree(node, {**ctx, alias: it})
                for it in (items if isinstance(items, list) else [])
            ]
        elif isinstance(v, dict) and "$if" in v:
            out[k] = resolve_ui_tree(v, ctx)
        elif isinstance(v, dict) and "type" in v and "props" in v:
            out[k] = resolve_ui_tree(v, ctx)
        else:
            out[k] = resolve_value(v, ctx)
    return out


def resolve_ui_tree(tree: dict, ctx: dict) -> dict:
    """Tier-2: pre-resolve a {type,props} tree against the binding context (server-side).

    Handles:
    - {{binding}} substitution in all prop values
    - $repeat directive: expands a list expression into per-item nodes
    - $if directive: keeps or drops a node based on a condition
    Nested {type, props} children are resolved recursively.
    """
    if "$if" in tree:
        keep = _eval_if(tree["$if"], ctx)
        if not keep:
            return {}
        tree = tree["node"]

    return {"type": tree["type"], "props": _resolve_props(tree.get("props", {}), ctx)}
