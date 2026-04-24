# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Extension validator — instance-level rules (V1, V2, V3, V8, V9, V12, V13).

Used by ``imperal validate`` CLI and kernel loader. Returns a structured
report with errors, warnings, and info entries.

v2.0.0 scope
------------
Legacy V4/V5/V6/V7/V10/V11 iterated over ``@chat.function`` definitions
collected from ``ext._chat_extensions``. ChatExtension was removed in
SDK v2.0.0, so those rules have no data to check and their intent is
now enforced structurally — see V14 (source-tree AST scan) in
``imperal_sdk.validators.v14_no_chatext``.

Source-tree AST rules (V14, SKEL-GUARD-*, CACHE-MODEL-*, etc.) live in
sibling modules and are invoked by the CLI ``validate`` command, not by
``validate_extension()``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

APP_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+")


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
    """Validate an Extension instance against instance-level rules.

    Covers: V1 (app_id), V2 (version), V3 (at-least-one-tool), V8
    (imperal.json runtime placeholder), V9 (health check), V12 (on_install),
    V13 (skeleton naming convention).

    Source-tree AST rules (V14 in ``imperal_sdk.validators`` plus
    SKEL-GUARD-* / CACHE-MODEL-* / MANIFEST-* from
    ``validator_v1_6_0``) are invoked separately by the CLI ``validate``
    command.

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

    # v2.0.0: ChatExtension removed. All extensions are pure tool providers;
    # every user-facing prose call is rendered kernel-side by Webbee Narrator.
    # The legacy V4/V5/V6/V7/V10/V11 rules operated on ``@chat.function``
    # definitions collected from ``ext._chat_extensions`` — in v2 that
    # dict is gone, those rules have no data to check, and their intent is
    # now enforced structurally (V14 rejects the class, Webbee Narrator is
    # the sole LLM caller so V7-style "no direct anthropic import" in an
    # extension no longer has a runtime vector). Legacy tests that targeted
    # them have been removed along with ChatExtension in Task 2.
    #
    # Only generic Extension rules remain: V1, V2, V3 (at-least-one tool),
    # V8, V9, V12, V13, V14.
    report.function_count = 0

    # V3: must have at least one @ext.tool
    if not tools:
        report.issues.append(ValidationIssue(
            rule="V3", level="ERROR",
            message="Extension must have at least one @ext.tool",
            fix="Register a tool with @ext.tool(description=..., output_schema=...)",
        ))

    # Event count: @ext.on_event handlers only (v2 has no @chat.function events)
    event_count = 0
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

    return report
