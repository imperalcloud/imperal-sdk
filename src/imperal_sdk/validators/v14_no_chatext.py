# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""V14 — reject v1-style extensions.

Checks performed on an extension source tree:
  1. No Python file imports ``ChatExtension`` from ``imperal_sdk``.
  2. No Python file references ``imperal_sdk.ChatExtension`` via attribute
     access.
  3. No class body contains a ``_system_prompt`` assignment.
  4. No module body contains a ``_system_prompt`` assignment.
  5. No ``@ext.tool`` (or any call) has ``llm_orchestrator=True`` keyword.
  6. No ``prompts/system_prompt.txt`` file exists.
  7. No ``prompts/intake.txt`` file exists.

All seven patterns are v1-era markers removed in SDK v2.0.0. Webbee
Narrator (kernel-side) is the sole voice surface; extensions are pure
tool providers.

Invariants enforced:
  - I-LOADER-REJECT-CHATEXT
  - I-LOADER-REJECT-SYSTEM-PROMPT
  - I-LOADER-REJECT-ORCHESTRATOR

Spec: ``docs/superpowers/specs/2026-04-24-webbee-single-voice-design.md``
§10.3.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class V14Result:
    """Outcome of a single V14 scan.

    ``passed`` is True iff no v1-era markers were found. ``issues`` carries
    one human-readable line per detection, prefixed with
    ``<relative_path>:<line>`` when applicable. An empty ``issues`` list
    MUST imply ``passed=True``.
    """

    passed: bool
    issues: list[str] = field(default_factory=list)


def _check_prompt_file(ext_dir: Path, rel: str, remediation: str) -> str | None:
    """Return a V14 issue string if ``<ext_dir>/<rel>`` exists, else None."""
    f = ext_dir / rel
    if f.exists():
        return f"{rel}: {remediation}"
    return None


def _scan_python_file(ext_dir: Path, py_file: Path, issues: list[str]) -> None:
    """Walk a single Python file's AST, appending V14 issues in-place."""
    rel = py_file.relative_to(ext_dir)
    try:
        source = py_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        issues.append(f"{rel}: cannot read file ({e})")
        return

    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError as e:
        issues.append(f"{rel}: syntax error ({e})")
        return

    # Module-level _system_prompt assignments
    for mod_node in tree.body:
        if isinstance(mod_node, ast.Assign):
            for target in mod_node.targets:
                if isinstance(target, ast.Name) and target.id == "_system_prompt":
                    issues.append(
                        f"{rel}:{mod_node.lineno}: module-level _system_prompt "
                        "variable found. Removed in SDK v2.0.0 — Webbee Narrator "
                        "writes all user-facing prose."
                    )

    for node in ast.walk(tree):
        # Check 1: `from imperal_sdk import ChatExtension`
        if isinstance(node, ast.ImportFrom):
            if node.module == "imperal_sdk":
                for alias in node.names:
                    if alias.name == "ChatExtension":
                        issues.append(
                            f"{rel}:{node.lineno}: imports ChatExtension from "
                            "imperal_sdk. ChatExtension removed in SDK v2.0.0. "
                            "Subclass Extension and register tools with @ext.tool."
                        )

        # Check 2: `imperal_sdk.ChatExtension` attribute access
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "imperal_sdk"
                and node.attr == "ChatExtension"
            ):
                issues.append(
                    f"{rel}:{node.lineno}: references imperal_sdk.ChatExtension. "
                    "Removed in SDK v2.0.0."
                )

        # Check 3: class-level _system_prompt assignment
        if isinstance(node, ast.ClassDef):
            for class_body_node in node.body:
                if isinstance(class_body_node, ast.Assign):
                    for target in class_body_node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "_system_prompt"
                        ):
                            issues.append(
                                f"{rel}:{class_body_node.lineno}: class "
                                f"{node.name} defines _system_prompt attribute. "
                                "Removed in SDK v2.0.0 — Webbee Narrator writes "
                                "all user-facing prose."
                            )

        # Check 5: `llm_orchestrator=True` keyword argument in any call
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "llm_orchestrator":
                    # Only flag True / truthy constants. Passing a variable
                    # is legal (only `True` is the v1 marker).
                    is_true = False
                    if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        is_true = True
                    if is_true:
                        issues.append(
                            f"{rel}:{kw.value.lineno if hasattr(kw.value, 'lineno') else node.lineno}: "
                            "llm_orchestrator=True keyword argument detected. "
                            "Per-extension orchestrator loops removed in SDK v2.0.0. "
                            "Webbee Narrator composes user-facing prose; extensions "
                            "expose tools only."
                        )


def run_v14(ext_dir: Path | str) -> V14Result:
    """Run V14 checks against an extension source tree.

    Scans ``ext_dir`` recursively for ``*.py`` files + the
    ``prompts/system_prompt.txt`` and ``prompts/intake.txt`` files. Accumulates
    all detections; does not short-circuit on first hit so a single pass
    produces a complete remediation list.

    Args:
        ext_dir: extension root (contains ``main.py`` / ``imperal.json`` /
            ``prompts/`` etc.). Accepts ``str`` or ``pathlib.Path``.

    Returns:
        V14Result with ``passed`` True iff zero issues detected.
    """
    ext_dir = Path(ext_dir)
    issues: list[str] = []

    # Filesystem markers: legacy prompt files.
    prompt_issue = _check_prompt_file(
        ext_dir,
        "prompts/system_prompt.txt",
        "ChatExtension-era system prompt file detected. "
        "Delete — Webbee Narrator handles voice in SDK v2.0.0.",
    )
    if prompt_issue:
        issues.append(prompt_issue)

    intake_issue = _check_prompt_file(
        ext_dir,
        "prompts/intake.txt",
        "ChatExtension-era intake prompt file detected. "
        "Delete — extensions cannot carry voice intake in SDK v2.0.0.",
    )
    if intake_issue:
        issues.append(intake_issue)

    # AST source scan.
    for py_file in ext_dir.rglob("*.py"):
        # Skip dot-dirs and common venv / cache folders.
        parts = py_file.relative_to(ext_dir).parts
        if any(p.startswith(".") or p in {"__pycache__", "venv", ".venv", "node_modules"} for p in parts):
            continue
        _scan_python_file(ext_dir, py_file, issues)

    return V14Result(passed=(len(issues) == 0), issues=issues)
