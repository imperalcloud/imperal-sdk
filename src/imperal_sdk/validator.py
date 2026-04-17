# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Extension validator — checks V1-V16 rules.

Used by `imperal validate` CLI and kernel loader.
Returns structured report with errors, warnings, and info.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

APP_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+")
VALID_ACTION_TYPES = {"read", "write", "destructive"}
_FN_PREFIX = "fn_"



# === PEP 563 / forward-reference helper (task #73) =====================
# Validator inspects function annotations. Under
# ``from __future__ import annotations`` (the Python 3.10+ default style)
# every annotation is a STRING, not a class. ``typing.get_type_hints``
# resolves those strings via the function's ``__globals__`` back to real
# classes; without it, ``isinstance(ann, type)`` is always False and every
# type-based check misfires (false positive on V6, false negative on V5).

def _resolve_hints(func) -> dict:
    """Return ``typing.get_type_hints(func)`` or ``{}`` on failure.

    Never raises. Failures are silent -- callers fall back to raw
    ``__annotations__`` when the hint dict is missing the key they need.
    """
    try:
        import typing
        return typing.get_type_hints(func)
    except Exception:
        # Common failure modes: circular imports, forward refs to private
        # classes, string annotations referencing modules not imported in
        # this context. None of them are validator bugs -- we degrade to
        # substring fallback and keep running.
        return {}


def _looks_like_action_result(value) -> bool:
    """True iff ``value`` is the ActionResult class or a subclass of it.

    Accepts class references (after PEP 563 resolution) AND string
    annotations (pre-resolution fallback). Substring match on 'ActionResult'
    is intentionally lenient -- subclasses, aliased re-exports, and
    typing.Union / Optional wrappers are all acceptable.
    """
    if value is None:
        return False
    # Class-level identity check (preferred -- strict).
    try:
        from imperal_sdk.chat.action_result import ActionResult as _AR
        if isinstance(value, type) and issubclass(value, _AR):
            return True
    except Exception:
        pass
    # String / str(value) fallback (substring -- lenient but correct).
    if "ActionResult" in str(value):
        return True
    return False


def _is_basemodel_subclass(value) -> bool:
    """True iff ``value`` is a Pydantic BaseModel subclass (post-resolution)."""
    if not isinstance(value, type):
        return False
    try:
        from pydantic import BaseModel
        return issubclass(value, BaseModel)
    except (TypeError, ImportError):
        return False


@dataclass
class ValidationIssue:
    """A single validation issue."""
    rule: str       # "V1", "V2", etc.
    level: str      # "ERROR", "WARN", "INFO"
    message: str
    file: str = ""
    line: int = 0
    fix: str = ""


@dataclass
class ValidationReport:
    """Result of validating an extension."""
    app_id: str
    version: str
    issues: list[ValidationIssue] = field(default_factory=list)
    function_count: int = 0
    tool_count: int = 0
    event_count: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "WARN"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate_extension(ext) -> ValidationReport:
    """Validate an Extension instance against V1-V16 rules.

    Args:
        ext: An Extension instance (with app_id, version, tools, etc.)

    Returns:
        ValidationReport with all issues found.
    """
    report = ValidationReport(
        app_id=getattr(ext, "app_id", "unknown"),
        version=getattr(ext, "version", "0.0.0"),
    )

    # V1: app_id format — must be [a-z0-9][a-z0-9-]*[a-z0-9], min 2 chars
    app_id = getattr(ext, "app_id", "")
    if not app_id or not APP_ID_PATTERN.match(app_id):
        safe = app_id.lower().replace(" ", "-") if app_id else ""
        fix_msg = f"Change app_id to '{safe}'" if safe else "Set app_id to a valid lowercase identifier"
        report.issues.append(ValidationIssue(
            rule="V1", level="ERROR",
            message=f"app_id '{app_id}' must match [a-z0-9][a-z0-9-]*[a-z0-9] (2+ chars, no uppercase)",
            fix=fix_msg,
        ))

    # V2: version must be semver
    version = getattr(ext, "version", "")
    if not version or not SEMVER_PATTERN.match(version):
        report.issues.append(ValidationIssue(
            rule="V2", level="ERROR",
            message=f"version '{version}' must be valid semver (e.g. '1.0.0')",
            fix="Set version to a valid semver string",
        ))

    # Count registered @ext.tool entries
    tools = getattr(ext, "_tools", {})
    report.tool_count = len(tools)

    # Collect all ChatExtension instances registered on this extension
    chat_extensions: dict = getattr(ext, "_chat_extensions", {})

    # Aggregate all @chat.function definitions across every ChatExtension
    functions: dict = {}
    for ce in chat_extensions.values():
        funcs = getattr(ce, "_functions", {})
        functions.update(funcs)
    report.function_count = len(functions)

    # V3: must have at least one @ext.tool or ChatExtension
    if not tools and not chat_extensions:
        report.issues.append(ValidationIssue(
            rule="V3", level="ERROR",
            message="Extension must have at least one @ext.tool or ChatExtension",
            fix="Add a @ext.tool or create a ChatExtension",
        ))

    # V4, V5, V6, V10, V11: check each @chat.function
    for fname, fdef in functions.items():
        # V4: explicit action_type
        action_type = getattr(fdef, "action_type", "")
        if action_type not in VALID_ACTION_TYPES:
            report.issues.append(ValidationIssue(
                rule="V4", level="ERROR",
                message=(
                    f"@chat.function '{fname}' must have explicit action_type "
                    f"('read', 'write', or 'destructive'), got '{action_type}'"
                ),
                fix=f"Add action_type='read' (or 'write'/'destructive') to @chat.function('{fname}')",
            ))

        # V5: must return ActionResult -- PEP 563 safe.
        # Resolve hints first (handles string annotations); if that
        # fails or the hint dict lacks 'return', fall back to raw
        # __annotations__ substring check so V5 still fires on missing
        # annotations entirely.
        func = getattr(fdef, "func", None)
        if func:
            _v5_hints = _resolve_hints(func)
            _v5_ret = _v5_hints.get("return")
            _v5_raw = getattr(func, "__annotations__", {}).get("return", "")
            _v5_ok = _looks_like_action_result(_v5_ret) or (
                _v5_ret is None and "ActionResult" in str(_v5_raw)
            )
            if not _v5_ok:
                report.issues.append(ValidationIssue(
                    rule="V5", level="ERROR",
                    message=f"@chat.function '{fname}' must return ActionResult",
                    fix="Add return type annotation: -> ActionResult",
                ))

        # V6: params should be Pydantic BaseModel (WARN for now, ERROR in v2)
        # PEP 563 safe: resolve annotations via typing.get_type_hints so
        # string annotations (Python 3.10+ default with
        # `from __future__ import annotations`) are resolved to real
        # classes before isinstance/issubclass checks.
        if func:
            import inspect
            sig = inspect.signature(func)
            params_list = [
                p for p in sig.parameters.values()
                if p.name not in ("ctx", "self")
            ]
            _v6_hints = _resolve_hints(func)
            has_pydantic_param = False
            for p in params_list:
                # Prefer resolved hint; fall back to raw annotation if
                # get_type_hints failed for this param (uncommon).
                resolved = _v6_hints.get(p.name, p.annotation)
                if resolved is inspect.Parameter.empty:
                    continue
                if _is_basemodel_subclass(resolved):
                    has_pydantic_param = True
                    break
            if params_list and not has_pydantic_param:
                report.issues.append(ValidationIssue(
                    rule="V6", level="WARN",
                    message=f"@chat.function '{fname}' params should be a Pydantic BaseModel subclass",
                    fix=(
                        f"Create a Pydantic model for params: "
                        f"class {fname.title().replace('_', '')}Params(BaseModel): ..."
                    ),
                ))

        # V10: write/destructive without event=
        event = getattr(fdef, "event", "")
        if action_type in ("write", "destructive") and not event:
            # Build suggested event name without backslash in f-string
            short_name = fname[len(_FN_PREFIX):] if fname.startswith(_FN_PREFIX) else fname
            suggested_event = f"{app_id}.{short_name}"
            report.issues.append(ValidationIssue(
                rule="V10", level="WARN",
                message=f"@chat.function '{fname}' (action_type='{action_type}') has no event=",
                fix=f"Add event='{suggested_event}' to the decorator",
            ))

        # V11: missing docstring
        func = getattr(fdef, "func", None)
        if func and not getattr(func, "__doc__", None):
            report.issues.append(ValidationIssue(
                rule="V11", level="WARN",
                message=f"@chat.function '{fname}' missing docstring",
                fix="Add a docstring to the function",
            ))

    # V7: no direct import anthropic/openai — check each ChatExtension's module source
    for ce in chat_extensions.values():
        tool_func = getattr(ce, "_entry_func", None) or getattr(ce, "_handle", None)
        if tool_func:
            import inspect
            try:
                source = inspect.getsource(inspect.getmodule(tool_func))
                for banned in ("import anthropic", "import openai", "from anthropic", "from openai"):
                    if banned in source:
                        report.issues.append(ValidationIssue(
                            rule="V7", level="ERROR",
                            message=f"Direct '{banned}' found. Use ctx.ai or get_llm_provider() instead",
                            fix="Replace direct LLM imports with ctx.ai.complete() or get_llm_provider()",
                        ))
                        break
            except (TypeError, OSError):
                pass

    # Count events: functions with event= + @ext.on_event handlers
    event_count = sum(1 for f in functions.values() if getattr(f, "event", ""))
    for _eh in getattr(ext, "_event_handlers", []):
        event_count += 1
    report.event_count = event_count

    # V8: imperal.json manifest check — filesystem only, warn in runtime validation
    report.issues.append(ValidationIssue(
        rule="V8", level="WARN",
        message="Cannot verify imperal.json manifest (runtime validation)",
        fix="Run 'imperal validate ./extension' from CLI for full filesystem check",
    ))

    # V9: missing @ext.health_check
    if getattr(ext, "_health_check", None) is None:
        report.issues.append(ValidationIssue(
            rule="V9", level="WARN",
            message="No @ext.health_check registered",
            fix="Add @ext.health_check decorator to a health check function",
        ))

    # V12: no on_install lifecycle hook
    lifecycle = getattr(ext, "_lifecycle", {})
    if "on_install" not in lifecycle:
        report.issues.append(ValidationIssue(
            rule="V12", level="INFO",
            message="No @ext.on_install lifecycle hook",
            fix="Consider adding @ext.on_install for first-time setup",
        ))

    return report
