# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Imperal Cloud SDK CLI."""
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
    """Validate manifest before deploy. Returns list of errors."""
    errors = []
    for tool in manifest.get("tools", []):
        if not tool.get("description"):
            errors.append(f"Tool '{tool['name']}' has no description — embeddings will fail")
        for scope in tool.get("scopes", []):
            if not re.match(r'^[a-z_]+(\.[a-z_]+)*$', scope):
                errors.append(f"Invalid scope format: '{scope}' — use dot.notation (e.g. 'cases.read')")
    return errors


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """Imperal Cloud SDK — build extensions for the Imperal platform."""
    pass


@cli.command()
@click.argument("name")
@click.option("--template", type=click.Choice(["chat", "tool"]), default="chat", help="Extension template")
def init(name: str, template: str):
    """Scaffold a new extension project."""
    os.makedirs(name, exist_ok=True)
    os.makedirs(f"{name}/tests", exist_ok=True)

    if template == "chat":
        main_content = f'''"""{name} — Imperal Cloud Extension."""
from pydantic import BaseModel
from imperal_sdk import Extension, ChatExtension, ActionResult

ext = Extension("{name}", version="1.0.0")
chat = ChatExtension(ext, tool_name="{name}", description="{name.replace('-', ' ').title()} extension")


class GreetParams(BaseModel):
    name: str = "World"


@chat.function("greet", description="Say hello", params={{}}, action_type="read")
async def fn_greet(ctx, params: GreetParams) -> ActionResult:
    """Greet someone by name."""
    return ActionResult.success(
        data={{"message": f"Hello, {{params.name}}!"}},
        summary=f"Greeted {{params.name}}",
    )
'''
    else:
        main_content = f'''"""{name} — Imperal Cloud Extension."""
from imperal_sdk import Extension

ext = Extension("{name}", version="1.0.0")


@ext.tool("{name}", description="{name.replace('-', ' ').title()}")
async def hello(ctx, name: str = "World"):
    """Say hello."""
    return {{"message": f"Hello, {{name}}!"}}
'''

    with open(f"{name}/main.py", "w") as f:
        f.write(main_content)

    with open(f"{name}/requirements.txt", "w") as f:
        f.write("imperal-sdk>=1.0.0\n")

    with open(f"{name}/tests/__init__.py", "w") as f:
        pass

    test_content = f'''"""Tests for {name} extension."""
import pytest
from imperal_sdk.testing import MockContext
from main import ext


def test_extension_registered():
    assert ext.app_id == "{name}"
    assert ext.version == "1.0.0"
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

        from imperal_sdk.validator import validate_extension
        report = validate_extension(ext)

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
