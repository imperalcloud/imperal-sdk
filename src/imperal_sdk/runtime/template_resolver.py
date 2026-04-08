import re
import logging

logger = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"\{\{(.+?)\}\}")


def _format_dict(d: dict) -> str:
    """Format a dict as readable text for template resolution.

    Priority: response key (Hub agent output) > summary key > readable lines.
    """
    if "response" in d:
        return str(d["response"])
    if "summary" in d:
        return str(d["summary"])
    # Format as readable key: value lines, skip internal fields
    parts = []
    for k, v in d.items():
        if k.startswith("_"):
            continue
        parts.append(f"{k}: {v}")
    return "\n".join(parts) if parts else str(d)


def _format_list(lst: list) -> str:
    """Format a list as readable text for template resolution."""
    if all(isinstance(item, dict) for item in lst):
        # List of dicts — numbered lines with key: value pairs
        parts = []
        for i, item in enumerate(lst, 1):
            item_str = ", ".join(f"{k}: {v}" for k, v in item.items() if not str(k).startswith("_"))
            parts.append(f"{i}. {item_str}")
        return "\n".join(parts)
    return ", ".join(str(item) for item in lst)


def resolve_dot_path(context: dict, path: str):
    """Resolve a dot-separated path against a nested dict/list structure.
    
    Examples:
        resolve_dot_path(ctx, "steps.1.data.message_id") -> "abc"
        resolve_dot_path(ctx, "steps.1.data.emails.0.from") -> "x@y.com"
    
    Returns the resolved value, or "" if any segment is missing.
    When the final value is a dict or list, formats it as readable text.
    """
    parts = path.strip().split(".")
    current = context
    for part in parts:
        if current is None:
            return ""
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (IndexError, ValueError):
                return ""
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return ""
    if current is None:
        return ""

    # Smart formatting for complex types
    if isinstance(current, dict):
        return _format_dict(current)

    if isinstance(current, list):
        return _format_list(current)

    return current


def resolve_template(template: str, context: dict) -> str:
    """Replace all {{path.to.var}} with resolved values from context.
    
    Missing values resolve to empty string.
    Dicts/lists are formatted as readable text (not raw Python repr).
    """
    def _replace(match):
        path = match.group(1).strip()
        value = resolve_dot_path(context, path)
        # resolve_dot_path already formats dicts/lists as readable strings
        return str(value) if value != "" else ""
    
    return _TEMPLATE_RE.sub(_replace, template)


def resolve_params(params: dict, context: dict) -> dict:
    """Resolve all string values in a params dict."""
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str):
            resolved[key] = resolve_template(value, context)
        else:
            resolved[key] = value
    return resolved
