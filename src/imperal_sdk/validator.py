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

    # V13: tool names starting with "refresh_" that are NOT prefixed
    # "skeleton_refresh_" will not be picked up by the kernel's auto-derive
    # skeleton_sections convention. They'll run only if the Registry has an
    # explicit skeleton_sections row pointing at them — easy to forget.
    # Recommend renaming via @ext.skeleton("<section>") sugar or @ext.tool
    # with the skeleton_refresh_ prefix so the platform auto-wires them.
    # See skeleton.md §"Skeleton Refresh Tools".
    _tools = getattr(ext, "_tools", {})
    for tool_name in _tools.keys():
        if not isinstance(tool_name, str):
            continue
        if tool_name.startswith("refresh_") and not tool_name.startswith("skeleton_refresh_"):
            suggested = tool_name[len("refresh_"):]
            report.issues.append(ValidationIssue(
                rule="V13", level="WARN",
                message=(
                    f"Tool {tool_name!r} looks like a skeleton refresh but lacks "
                    f"the 'skeleton_refresh_' prefix required by the kernel's "
                    f"auto-derive convention"
                ),
                fix=(
                    f"Rename to 'skeleton_refresh_{suggested}' OR use "
                    f"@ext.skeleton({suggested!r}) decorator which applies the "
                    f"convention automatically"
                ),
            ))
        # Likewise for alert counterparts — kernel expects skeleton_alert_<X>
        # as the paired alert activity when a refresh section has alert_on_change.
        if tool_name.startswith("alert_") and not tool_name.startswith("skeleton_alert_"):
            suggested = tool_name[len("alert_"):]
            report.issues.append(ValidationIssue(
                rule="V13", level="INFO",
                message=(
                    f"Tool {tool_name!r} looks like a skeleton alert but lacks "
                    f"the 'skeleton_alert_' prefix"
                ),
                fix=(
                    f"Rename to 'skeleton_alert_{suggested}' so the kernel "
                    f"auto-wires it when refresh section has alert_on_change=True"
                ),
            ))

    # === Federal v4.0.0 contract — V14-V24 =============================
    # Goal: every extension that passes these is GUARANTEED to work with
    # the kernel's typed-dispatch chain pipeline. No silent write failures,
    # no LLM-router guessing, no hallucinated capabilities.

    display_name = getattr(ext, "display_name", "") or ""
    description = getattr(ext, "description", "") or ""
    icon_path = getattr(ext, "icon", "") or ""
    actions_explicit = getattr(ext, "actions_explicit", True)

    # V14 — extension description ≥40 chars, ≠ app_id
    if not description or len(description.strip()) < 40 or description.strip() == app_id:
        report.issues.append(ValidationIssue(
            rule="V14", level="ERROR",
            message=(
                f"Extension {app_id!r} description must be ≥40 chars and "
                f"≠ app_id (got len={len(description)}, value={description!r:.40})"
            ),
            fix=(
                "Set Extension(description=...) to a sentence describing what "
                "the extension does. Webbee shows this in 'что я умею?' — "
                "without it the user sees a bare slug. Federal V14."
            ),
        ))

    # V15 — extension display_name ≥3 chars, ≠ app_id (case-sensitive verbatim)
    if not display_name or len(display_name.strip()) < 3:
        report.issues.append(ValidationIssue(
            rule="V15", level="ERROR",
            message=(
                f"Extension {app_id!r} display_name must be ≥3 chars "
                f"(got len={len(display_name)}, value={display_name!r})"
            ),
            fix=(
                "Set Extension(display_name='Notes') — human-readable, "
                "NOT the slug. Federal V15."
            ),
        ))
    elif display_name.strip() == app_id:
        report.issues.append(ValidationIssue(
            rule="V15", level="ERROR",
            message=(
                f"Extension display_name {display_name!r} verbatim equals "
                f"app_id {app_id!r} — provide human-readable name "
                f"(e.g. 'Notes' for app_id='notes')"
            ),
            fix="Use 'Notes' instead of 'notes', 'Mail Inbox' instead of 'mail-inbox', etc.",
        ))

    # V16 — every @chat.function description ≥20 chars (skip __* synthetic)
    chat_extensions: dict = getattr(ext, "_chat_extensions", {})
    for chat_tool_name, chat_ext in (chat_extensions or {}).items():
        for fn_name, fn_def in chat_ext.functions.items():
            if fn_name.startswith("__"):
                continue  # synthetic skip
            fn_desc = (fn_def.description or "").strip()
            if len(fn_desc) < 20:
                report.issues.append(ValidationIssue(
                    rule="V16", level="ERROR",
                    message=(
                        f"@chat.function {fn_name!r} (tool {chat_tool_name}) "
                        f"description must be ≥20 chars (got len={len(fn_desc)})"
                    ),
                    fix=(
                        "Set @chat.function(description='...') to a sentence "
                        "describing inputs, outputs, and when to use it. The "
                        "LLM uses this to choose tools. Federal V16."
                    ),
                ))

    # V17 — every @chat.function has explicit Pydantic params model
    for chat_tool_name, chat_ext in (chat_extensions or {}).items():
        for fn_name, fn_def in chat_ext.functions.items():
            if fn_name.startswith("__"):
                continue
            if getattr(fn_def, "_pydantic_model", None) is None:
                report.issues.append(ValidationIssue(
                    rule="V17", level="ERROR",
                    message=(
                        f"@chat.function {fn_name!r} must declare a Pydantic "
                        f"BaseModel param (federal V17 — no **kwargs, no Any)"
                    ),
                    fix=(
                        "Define `class XParams(BaseModel): ...` and use it as "
                        "the typed handler arg: `async def fn(ctx, params: XParams)`. "
                        "SDK auto-derives params schema from the model."
                    ),
                ))

    # V18 — every @chat.function returns Pydantic model (subclass of ActionResult)
    for chat_tool_name, chat_ext in (chat_extensions or {}).items():
        for fn_name, fn_def in chat_ext.functions.items():
            if fn_name.startswith("__"):
                continue
            ret_model = getattr(fn_def, "_return_model", None)
            if ret_model is None:
                report.issues.append(ValidationIssue(
                    rule="V18", level="ERROR",
                    message=(
                        f"@chat.function {fn_name!r} must declare a Pydantic "
                        f"return type (subclass of ActionResult)"
                    ),
                    fix=(
                        "Annotate the handler return as `-> ActionResult` or a "
                        "subclass. Federal V18 — kernel reads return_schema from "
                        "manifest for typed dispatch."
                    ),
                ))

    # V19 — actions_explicit + chain_callable on writes/destructive
    if not actions_explicit:
        report.issues.append(ValidationIssue(
            rule="V19", level="ERROR",
            message=(
                f"Extension {app_id!r} must set actions_explicit=True "
                f"(federal v4.0.0 default)"
            ),
            fix=(
                "Set Extension(actions_explicit=True). Declares that every "
                "write/destructive @chat.function is chain-callable as a typed "
                "structured call — closes the chain_planner BYOLLM-router gap."
            ),
        ))
    else:
        for chat_tool_name, chat_ext in (chat_extensions or {}).items():
            for fn_name, fn_def in chat_ext.functions.items():
                if fn_name.startswith("__"):
                    continue
                if fn_def.action_type in ("write", "destructive") and not fn_def.chain_callable:
                    report.issues.append(ValidationIssue(
                        rule="V19", level="ERROR",
                        message=(
                            f"@chat.function {fn_name!r} (action_type={fn_def.action_type}) "
                            f"must have chain_callable=True under actions_explicit=True"
                        ),
                        fix=(
                            "Default is True for writes — only set chain_callable=False "
                            "if you genuinely need LLM-router routing (very rare)."
                        ),
                    ))

    # V20 — every write/destructive @chat.function declares effects (info-level
    # for v4.0.0, error-level v5.0.0). Effects power the audit ledger + narrator.
    for chat_tool_name, chat_ext in (chat_extensions or {}).items():
        for fn_name, fn_def in chat_ext.functions.items():
            if fn_name.startswith("__"):
                continue
            if fn_def.action_type in ("write", "destructive") and not fn_def.effects:
                report.issues.append(ValidationIssue(
                    rule="V20", level="WARN",
                    message=(
                        f"@chat.function {fn_name!r} ({fn_def.action_type}) "
                        f"should declare effects=['create:resource'] etc. "
                        f"(federal V20, error in v5.0.0)"
                    ),
                    fix=(
                        "Pass effects=['create:note'] or ['delete:folder'] etc. "
                        "Used by chain narrator + audit ledger."
                    ),
                ))

    # V21 — required SVG icon
    if not icon_path:
        report.issues.append(ValidationIssue(
            rule="V21", level="ERROR",
            message=(
                f"Extension {app_id!r} must declare icon='icon.svg' "
                f"(federal V21 — required SVG marketplace icon)"
            ),
            fix=(
                "Add an icon.svg file to your extension dir + set "
                "Extension(icon='icon.svg'). Must be valid SVG with viewBox, "
                "max 100KB, no embedded base64 raster."
            ),
        ))
    elif not icon_path.lower().endswith(".svg"):
        report.issues.append(ValidationIssue(
            rule="V21", level="ERROR",
            message=f"Extension icon {icon_path!r} must be SVG (.svg extension)",
            fix="Federal V21 — only SVG icons accepted. Convert raster to SVG.",
        ))
    else:
        # Validate icon file content if locatable
        import os as _os
        for candidate in (icon_path, _os.path.join(_os.getcwd(), icon_path)):
            if _os.path.exists(candidate):
                try:
                    sz = _os.path.getsize(candidate)
                    if sz > 100 * 1024:
                        report.issues.append(ValidationIssue(
                            rule="V21", level="ERROR",
                            message=f"Icon {icon_path!r} is {sz} bytes — max 100KB",
                            fix="Optimize SVG (remove metadata, simplify paths) or split assets.",
                        ))
                    with open(candidate, "rb") as _f:
                        head = _f.read(2048).decode("utf-8", errors="ignore").lower()
                    if "<svg" not in head:
                        report.issues.append(ValidationIssue(
                            rule="V21", level="ERROR",
                            message=f"Icon {icon_path!r} missing <svg> root element",
                            fix="Federal V21 — must be valid SVG XML.",
                        ))
                    if "viewbox" not in head:
                        report.issues.append(ValidationIssue(
                            rule="V21", level="ERROR",
                            message=f"Icon {icon_path!r} missing viewBox attribute",
                            fix="Federal V21 — viewBox required for multi-size rendering.",
                        ))
                    if "data:image" in head and "base64" in head:
                        report.issues.append(ValidationIssue(
                            rule="V21", level="ERROR",
                            message=f"Icon {icon_path!r} contains embedded base64 raster",
                            fix="Federal V21 — pure SVG only, no embedded PNG/JPEG.",
                        ))
                except OSError:
                    pass
                break

    # V22 — lifecycle hook signatures match SDK contract
    _LIFECYCLE_REQUIRED_KW = {
        "on_install": set(),
        "on_uninstall": set(),
        "on_refresh": {"message"},  # added in SDK 3.x; closes the on_refresh(message=) TypeError class
        "on_upgrade": {"from_version"},
    }
    lifecycle = getattr(ext, "_lifecycle", {}) or {}
    for hook_name, hook_def in lifecycle.items():
        required = _LIFECYCLE_REQUIRED_KW.get(hook_name)
        if required is None:
            continue
        try:
            import inspect as _insp
            sig = _insp.signature(hook_def.func)
            params = set(sig.parameters.keys())
            missing = required - params
            # Allow **kwargs to absorb everything
            has_var_kw = any(
                p.kind == _insp.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if missing and not has_var_kw:
                report.issues.append(ValidationIssue(
                    rule="V22", level="ERROR",
                    message=(
                        f"Lifecycle hook {hook_name!r} missing required kwargs: "
                        f"{sorted(missing)}. Closes the TypeError class where kernel "
                        f"passes message= but extension didn't expect it."
                    ),
                    fix=(
                        f"Add {', '.join(sorted(missing))}=None to the hook signature, "
                        f"or accept **kwargs."
                    ),
                ))
        except (ValueError, TypeError):
            pass

    # V23 — capabilities in known set (<app>:read, <app>:write, <app>:*)
    capabilities = getattr(ext, "capabilities", []) or []
    _CAP_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*:(read|write|admin|\*)$")
    for cap in capabilities:
        if not _CAP_PATTERN.match(cap):
            report.issues.append(ValidationIssue(
                rule="V23", level="ERROR",
                message=(
                    f"Capability {cap!r} must be '<namespace>:read|write|admin|*' format"
                ),
                fix=(
                    "Use 'notes:read', 'mail:write', 'admin:*', etc. "
                    "Federal V23 — kernel only grants known capability shapes."
                ),
            ))

    # V24 — handler bodies must NOT access ctx.skeleton.* for data reads
    # (skeleton is LLM-only context cache; handlers use ctx.api).
    # AST static analysis on each @chat.function body.
    import ast as _ast
    import inspect as _insp
    _SKELETON_ACCESS_PATTERN = re.compile(r"\bctx\s*\.\s*skeleton\b")
    for chat_tool_name, chat_ext in (chat_extensions or {}).items():
        for fn_name, fn_def in chat_ext.functions.items():
            if fn_name.startswith("__"):
                continue
            try:
                src = _insp.getsource(fn_def.func)
            except (OSError, TypeError):
                continue
            if _SKELETON_ACCESS_PATTERN.search(src):
                report.issues.append(ValidationIssue(
                    rule="V24", level="ERROR",
                    message=(
                        f"@chat.function {fn_name!r} reads from ctx.skeleton — "
                        f"federal V24 forbids this. Skeleton is the LLM context "
                        f"cache (read by router/narrator), not a data source."
                    ),
                    fix=(
                        "Use ctx.api.<...>() to fetch from the real backend. "
                        "Skeleton is updated AFTER actions via @ext.skeleton "
                        "refresh functions, not read inline by handlers."
                    ),
                ))

    return report
