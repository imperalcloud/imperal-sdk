# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Imperal Cloud SDK CLI."""
import json
import os
import re
import sys
import configparser
import click
import httpx


def _load_credentials() -> dict:
    """Load credentials from .imperal/credentials or environment variables."""
    creds = {
        "registry_url": os.getenv("IMPERAL_REGISTRY_URL", ""),
        "gateway_url": os.getenv("IMPERAL_GATEWAY_URL", ""),
        "api_key": os.getenv("IMPERAL_API_KEY", ""),
    }
    creds_file = os.path.join(os.getcwd(), ".imperal", "credentials")
    if not os.path.exists(creds_file):
        creds_file = os.path.expanduser("~/.imperal/credentials")
    if os.path.exists(creds_file):
        cp = configparser.ConfigParser()
        cp.read(creds_file)
        section = "default"
        if cp.has_section(section):
            if not creds["registry_url"]:
                creds["registry_url"] = cp.get(section, "registry_url", fallback="")
            if not creds["gateway_url"]:
                creds["gateway_url"] = cp.get(section, "gateway_url", fallback="")
            if not creds["api_key"]:
                creds["api_key"] = cp.get(section, "api_key", fallback="")
    return creds


def _validate_manifest(manifest: dict) -> list[str]:
    """Validate manifest before deploy. Returns list of errors.

    Combines structural JSON-Schema validation (from `manifest_schema`) with
    deploy-specific checks (missing tool descriptions break embeddings).
    """
    from imperal_sdk.manifest_schema import validate_manifest_dict

    errors: list[str] = []

    # Structural contract — app_id / version / scope / cron / shape
    for issue in validate_manifest_dict(manifest):
        errors.append(f"[{issue.rule}] {issue.message}")

    # Deploy-only: embeddings depend on non-empty tool descriptions
    for tool in manifest.get("tools", []):
        if not tool.get("description"):
            errors.append(f"Tool '{tool.get('name', '?')}' has no description — embeddings will fail")

    return errors


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Imperal Cloud SDK — build extensions for the Imperal platform."""
    pass


@cli.command()
@click.argument("name")
@click.option(
    "--template",
    type=click.Choice(["chat", "tool"]),
    default="chat",
    help=(
        "Extension template. v2.0.0: 'chat' and 'tool' produce the same "
        "v2-style scaffold (ChatExtension removed). The 'chat' alias is "
        "kept for CLI backward compatibility."
    ),
)
def init(name: str, template: str):
    """Scaffold a new extension project.

    v2.0.0: extensions are pure tool providers. Both ``--template chat``
    and ``--template tool`` emit a class-based ``Extension`` subclass that
    registers one example tool via ``@ext.tool`` with an ``output_schema``
    Pydantic model. Webbee Narrator (kernel-side) renders all user-facing
    prose; no per-extension system prompt is permitted.
    """
    os.makedirs(name, exist_ok=True)
    os.makedirs(f"{name}/tests", exist_ok=True)

    # Class name: "my-test-ext" -> "MyTestExt"
    class_name = "".join(word.capitalize() for word in re.split(r"[-_]", name) if word)
    if not class_name:
        class_name = "MyExtension"

    # v2.0.0 scaffold: class-based Extension subclass (recommended shape) with
    # module-level ``ext`` instance exported so CLI commands `dev`/`validate`/
    # `deploy` can `from main import ext` uniformly. Both --template chat and
    # --template tool emit the same scaffold; the --chat flag is retained as
    # a CLI-level alias for UX familiarity.
    # Note: `from imperal_sdk import ext as _ext` avoids shadowing the
    # module-level decorator namespace with the local instance.
    main_content = f'''"""{name} — Imperal Cloud Extension (SDK v2.0.0)."""
from imperal_sdk import Extension, ext as _ext
from pydantic import BaseModel


class ExampleResult(BaseModel):
    """Output schema for the example tool."""

    message: str


class {class_name}(Extension):
    app_id = "{name}"
    version = "1.0.0"

    @_ext.tool(
        description="Example tool — replace with actual functionality description",
        output_schema=ExampleResult,
    )
    async def example_tool(self, ctx, who: str = "World") -> ExampleResult:
        """Greet someone by name."""
        return ExampleResult(message=f"Hello, {{who}}!")


# Instance exported for the CLI (`imperal dev` / `imperal validate` /
# `imperal deploy`). Webbee Narrator renders user-facing prose; extensions
# are pure tool providers.
ext = {class_name}(app_id="{name}", version="1.0.0")
'''

    with open(f"{name}/main.py", "w") as f:
        f.write(main_content)

    with open(f"{name}/requirements.txt", "w") as f:
        f.write("imperal-sdk>=1.0.0\n")

    with open(f"{name}/tests/__init__.py", "w") as f:
        pass

    test_content = f'''"""Tests for {name} extension."""
from main import ext


def test_extension_registered():
    assert ext.app_id == "{name}"
    assert ext.version == "1.0.0"


def test_example_tool_registered():
    # v2.0.0: @ext.tool stamps _tool_meta on the function object; the
    # subclass __init_subclass__ collects them into cls._tools_registry.
    assert "example_tool" in type(ext)._tools_registry
'''

    with open(f"{name}/tests/test_main.py", "w") as f:
        f.write(test_content)

    with open(f"{name}/.gitignore", "w") as f:
        f.write("venv/\n__pycache__/\n*.pyc\n.env\n.imperal/\n")

    click.echo(f"Extension '{name}' created! (template: {template})")
    click.echo(f"  cd {name}")
    click.echo(f"  pip install imperal-sdk")
    click.echo(f"  imperal validate")
    click.echo(f"  imperal dev")


@cli.command()
def dev():
    """Run local development server with hot reload."""
    sys.path.insert(0, ".")
    try:
        from main import ext
        from imperal_sdk.manifest import generate_manifest
        manifest = generate_manifest(ext)
        click.echo(f"Extension: {ext.app_id} v{ext.version}")
        click.echo(f"Tools: {', '.join(ext.tools.keys()) or 'none'}")
        click.echo(f"Signals: {', '.join(ext.signals.keys()) or 'none'}")
        click.echo(f"Schedules: {', '.join(ext.schedules.keys()) or 'none'}")
        click.echo("Dev server ready. Ctrl+C to stop.")
    except ImportError:
        click.echo("Error: No main.py found with 'ext' Extension object.", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("path", default=".")
def build(path: str):
    """Generate imperal.json manifest for the extension at PATH.

    Loads the extension from main.py, generates the manifest from registered
    tools/signals/schedules, merges any existing marketplace fields from
    imperal.json, and writes the result to imperal.json.
    """
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        click.echo(f"Error: Path '{path}' is not a directory.", err=True)
        raise SystemExit(1)

    original_dir = os.getcwd()
    try:
        os.chdir(abs_path)
        sys.path.insert(0, abs_path)
        try:
            # Re-import fresh so multiple builds in one session don't cache stale
            import importlib
            if "main" in sys.modules:
                del sys.modules["main"]
            import main as ext_module
        except ImportError as e:
            click.echo(f"Error: Could not load main.py from '{path}': {e}", err=True)
            raise SystemExit(1)

        # Find Extension instance
        from imperal_sdk.extension import Extension
        ext_obj = None
        for attr_name in dir(ext_module):
            obj = getattr(ext_module, attr_name)
            if isinstance(obj, Extension):
                ext_obj = obj
                break

        if ext_obj is None:
            click.echo(f"Error: No Extension instance found in '{path}/main.py'.", err=True)
            raise SystemExit(1)

        from imperal_sdk.manifest import save_manifest
        out_path = save_manifest(ext_obj, abs_path)

        tool_count = len(ext_obj.tools)
        signal_count = len(ext_obj.signals)
        schedule_count = len(ext_obj.schedules)

        click.echo(f"Built: {ext_obj.app_id} v{ext_obj.version}")
        click.echo(f"  Tools: {tool_count}, Signals: {signal_count}, Schedules: {schedule_count}")
        click.echo(f"  Manifest: {out_path}")
    finally:
        os.chdir(original_dir)
        if abs_path in sys.path:
            sys.path.remove(abs_path)


@cli.command()
@click.argument("path", default=".")
def validate(path: str):
    """Validate extension against SDK v1.0.0 rules."""
    original_dir = os.getcwd()
    try:
        os.chdir(path)
        sys.path.insert(0, ".")
        try:
            from main import ext
        except ImportError:
            click.echo("Error: No main.py found with 'ext' Extension object.", err=True)
            raise SystemExit(1)

        from imperal_sdk.validator import validate_extension, ValidationIssue
        from imperal_sdk.manifest_schema import validate_manifest_dict
        from imperal_sdk.validator_v1_6_0 import (
            validate_source_tree,
            validate_manifest_v1_6_0,
        )
        from imperal_sdk.validators import run_v14
        report = validate_extension(ext)

        # v1.6.0 AST rules (SKEL-GUARD-*, CACHE-MODEL-1, CACHE-TTL-1,
        # MANIFEST-SKELETON-1) — source-level, independent of ext instance.
        source_root = os.getcwd()
        for issue in validate_source_tree(source_root):
            report.issues.append(issue)

        # V14 (v2.0.0): reject ChatExtension / _system_prompt / intake prompts
        # / llm_orchestrator=True at source-tree level. See
        # imperal_sdk.validators.v14_no_chatext + tests/test_validator_v14.py.
        v14_result = run_v14(source_root)
        for issue_str in v14_result.issues:
            # Parse "path:line: rest" shape produced by run_v14 when possible;
            # fall back to message-only for filesystem-marker lines.
            file_part, line_no, message = "", 0, issue_str
            if ":" in issue_str:
                head, _, tail = issue_str.partition(": ")
                if ":" in head:
                    path_part, _, ln = head.rpartition(":")
                    if ln.isdigit():
                        file_part = path_part
                        line_no = int(ln)
                        message = tail
                    else:
                        file_part = head
                        message = tail
                else:
                    file_part = head
                    message = tail
            report.issues.append(ValidationIssue(
                rule="V14", level="ERROR",
                message=message,
                file=file_part,
                line=line_no,
                fix="Remove the v1-era marker — see SDK v2.0.0 migration guide.",
            ))

        # Close V8 — validate filesystem imperal.json if present. Replaces
        # the "runtime-only" V8 warning with concrete M1..M5 structural
        # issues from the JSON Schema contract.
        manifest_path = os.path.join(source_root, "imperal.json")
        if os.path.exists(manifest_path):
            # Drop the V8 placeholder warning — we have the real answer now.
            report.issues = [i for i in report.issues if i.rule != "V8"]
            try:
                with open(manifest_path) as f:
                    disk_manifest = json.load(f)
                for issue in validate_manifest_dict(disk_manifest):
                    issue.file = "imperal.json"
                    report.issues.append(issue)
                # SDK-VERSION-1 — cross-check sdk_version against source usage.
                for issue in validate_manifest_v1_6_0(disk_manifest, source_root):
                    report.issues.append(issue)
            except json.JSONDecodeError as e:
                report.issues.append(ValidationIssue(
                    rule="M0", level="ERROR",
                    message=f"imperal.json is not valid JSON: {e}",
                    file="imperal.json", line=e.lineno,
                    fix="Fix the JSON syntax error at the reported line",
                ))

        click.echo(f"\n── Imperal Extension Validator v1.0 {'─' * 40}")
        click.echo(f"\nExtension: {report.app_id} v{report.version}")
        click.echo(f"Tools: {report.tool_count}, Functions: {report.function_count}, Events: {report.event_count}")

        if not report.issues:
            click.echo("\n✅ No issues found!")
            return

        errors = report.errors
        warnings = report.warnings
        infos = [i for i in report.issues if i.level == "INFO"]

        click.echo(f"\nRESULTS: {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info")

        for issue in report.issues:
            prefix = {"ERROR": "  ERROR", "WARN": "  WARN ", "INFO": "  INFO "}[issue.level]
            loc = f" {issue.file}:{issue.line}" if issue.file else ""
            click.echo(f"\n  {prefix}{loc}  [{issue.rule}] {issue.message}")
            if issue.fix:
                click.echo(f"         Fix: {issue.fix}")

        if errors:
            click.echo(f"\n❌ {len(errors)} error(s) must be fixed before deployment.")
            raise SystemExit(1)
        else:
            click.echo(f"\n⚠️  {len(warnings)} warning(s) — consider fixing.")
    finally:
        os.chdir(original_dir)


@cli.command()
def test():
    """Run extension tests."""
    import subprocess
    result = subprocess.run(["python", "-m", "pytest", "tests/", "-v"])
    raise SystemExit(result.returncode)


@cli.command()
def deploy():
    """Deploy extension to Imperal Cloud.

    1. Generates manifest from Extension
    2. Validates tools (descriptions, scope format)
    3. Pushes tools + scopes to Registry
    4. Pushes config defaults to unified config store
    """
    sys.path.insert(0, ".")
    try:
        from main import ext
    except ImportError:
        click.echo("Error: No main.py found.", err=True)
        raise SystemExit(1)

    from imperal_sdk.manifest import generate_manifest, save_manifest

    manifest = generate_manifest(ext)
    save_manifest(ext)
    click.echo(f"Extension: {ext.app_id} v{ext.version}")

    errors = _validate_manifest(manifest)
    if errors:
        click.echo("Deploy blocked:", err=True)
        for e in errors:
            click.echo(f"  - {e}", err=True)
        raise SystemExit(1)

    creds = _load_credentials()
    if not creds["registry_url"] or not creds["api_key"]:
        click.echo("Error: Missing credentials. Set IMPERAL_REGISTRY_URL + IMPERAL_API_KEY or create .imperal/credentials", err=True)
        raise SystemExit(1)

    try:
        resp = httpx.get(
            f"{creds['registry_url']}/v1/apps/{ext.app_id}",
            headers={"x-api-key": creds["api_key"]},
            timeout=10,
        )
        if resp.status_code == 404:
            click.echo(f"Error: App '{ext.app_id}' not registered. Create it in Panel first.", err=True)
            raise SystemExit(1)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        click.echo(f"Error connecting to Registry: {e}", err=True)
        raise SystemExit(1)

    tools_payload = []
    for tool in manifest["tools"]:
        tools_payload.append({
            "activity": f"tool_{tool['name']}",
            "name": tool["name"].replace("_", " ").title(),
            "description": tool["description"],
            "domains": [],
            "required_scopes": tool.get("scopes", []),
        })

    skeleton_payload = []
    if "skeleton" in manifest.get("config_defaults", {}):
        for section_name, section_config in manifest["config_defaults"]["skeleton"].items():
            skeleton_payload.append({
                "section_name": section_name,
                "refresh_activity": section_config.get("refresh_activity", ""),
                "alert_activity": section_config.get("alert_activity", ""),
                "ttl": section_config.get("ttl", 300),
                "alert_on_change": section_config.get("alert_on_change", False),
            })

    try:
        resp = httpx.put(
            f"{creds['registry_url']}/v1/apps/{ext.app_id}/tools",
            json={"tools": tools_payload, "skeleton_sections": skeleton_payload, "version": ext.version},
            headers={"x-api-key": creds["api_key"]},
            timeout=30,
        )
        resp.raise_for_status()
        click.echo(f"Tools deployed: {len(tools_payload)} tools, {len(skeleton_payload)} skeleton sections")
    except httpx.HTTPError as e:
        click.echo(f"Error pushing tools: {e}", err=True)
        raise SystemExit(1)

    config_defaults = manifest.get("config_defaults", {})
    if config_defaults:
        try:
            resp = httpx.put(
                f"{creds['registry_url']}/v1/apps/{ext.app_id}/settings",
                json={k: v for k, v in config_defaults.items() if k != "skeleton"},
                headers={"x-api-key": creds["api_key"]},
                timeout=10,
            )
            resp.raise_for_status()
            click.echo("Config defaults deployed")
        except httpx.HTTPError as e:
            click.echo(f"Warning: Config deploy failed (non-fatal): {e}", err=True)

    click.echo(f"\nDeployed {ext.app_id} v{ext.version} successfully!")


@cli.command()
def logs():
    """Tail production logs."""
    click.echo("Connecting to Imperal Cloud logs...")
    click.echo("(Not yet implemented — will stream from SigNoz)")


if __name__ == "__main__":
    cli()
