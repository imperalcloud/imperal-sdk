# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Imperal Cloud SDK CLI."""
import json
import os
import re
import sys
import configparser
import click
import httpx

try:
    from imperal_sdk import __version__ as SDK_VERSION
except Exception:  # pragma: no cover - defensive
    SDK_VERSION = "5.x"


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
@click.version_option(version=SDK_VERSION)
def cli():
    """Imperal Cloud SDK — build extensions for the Imperal platform."""
    pass


@cli.command()
@click.argument("name")
@click.option("--template", type=click.Choice(["chat", "tool"]), default="chat", help="Extension template")
def init(name: str, template: str):
    """Scaffold a new extension project (federal v5 contract)."""
    os.makedirs(name, exist_ok=True)
    os.makedirs(f"{name}/tests", exist_ok=True)

    # `name` is the TARGET DIRECTORY; the app identity derives from its
    # basename — `imperal init ~/code/my-app` must scaffold app_id "my-app",
    # not a path (V1/M4 reject slashes; found by the 5.9.5 fresh-app E2E).
    app_id = os.path.basename(os.path.normpath(name))
    title = app_id.replace("-", " ").replace("_", " ").title()
    # M5: tool identifiers must be valid identifiers — an app_id like
    # "my-cool-app" scaffolded a tool literally named "my-cool-app", so a
    # fresh author hit a validation error before writing any code
    # (found by the 5.9.5 fresh-app E2E). The app_id itself keeps hyphens.
    ident = re.sub(r"[^0-9a-zA-Z_]", "_", app_id)
    if ident and ident[0].isdigit():
        ident = f"x_{ident}"
    # V14 requires description ≥40 chars, V15 requires display_name ≥3 chars
    # ≠ app_id, V16 requires per-function description ≥20 chars. We seed
    # values that satisfy all three so `imperal build && imperal validate`
    # passes immediately — no surprises for new authors.
    display_name = f"{title} Extension"
    description = (
        f"{title} — a starter extension scaffolded by `imperal init`. "
        f"Replace this description with something specific to your tool."
    )

    if template == "chat":
        main_content = f'''"""{title} extension — Imperal Cloud."""
from pydantic import BaseModel, Field
from imperal_sdk import Extension, ChatExtension, ActionResult


# Federal v5 Extension surface — V14 (description ≥40 chars), V15
# (display_name ≥3 chars, ≠ app_id), V19 (actions_explicit=True), and
# V21 (icon.svg required, XML <svg> root + viewBox) are all satisfied
# by these defaults. Edit display_name + description before publish.
ext = Extension(
    "{app_id}",
    version="1.0.0",
    display_name={display_name!r},
    description={description!r},
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[{app_id!r} + ":read"],
)

chat = ChatExtension(
    ext,
    tool_name={ident!r},
    description={f"{title} — chat tool entrypoint."!r},
)


class GreetParams(BaseModel):
    """Pydantic params model — V17 federal: typed BaseModel param required."""
    name: str = Field(default="World", description="Person to greet")


class GreetResult(BaseModel):
    """Typed return shape — V23 federal: read tools declare a data_model so
    the platform can validate $REF paths and prevent naming drift."""
    message: str = Field(description="The rendered greeting")


@chat.function(
    "greet",
    action_type="read",
    data_model=GreetResult,
    description="Greet someone by name with a friendly message.",
)
async def fn_greet(ctx, params: GreetParams) -> ActionResult:
    """Echo a greeting to verify the extension loads + validators pass."""
    return ActionResult.success(
        data={{"message": f"Hello, {{params.name}}!"}},
        summary=f"Greeted {{params.name}}",
    )
'''
    else:
        main_content = f'''"""{title} extension — Imperal Cloud (tool template, no chat surface)."""
from imperal_sdk import Extension


ext = Extension(
    "{app_id}",
    version="1.0.0",
    display_name={display_name!r},
    description={description!r},
    icon="icon.svg",
    actions_explicit=True,
    capabilities=[{app_id!r} + ":read"],
)


@ext.tool({ident!r}, scopes=[{app_id!r} + ":read"], description={f"{title} — invoke from automations or chains."!r})
async def fn_default(ctx, **kwargs):
    """Stub tool. Replace with your own."""
    return {{"message": "ok"}}
'''

    with open(f"{name}/main.py", "w") as f:
        f.write(main_content)

    # V21 federal: extensions MUST ship a valid SVG icon. We seed a tiny
    # placeholder that passes the validator (XML root + viewBox + ≤100 KB).
    with open(f"{name}/icon.svg", "w") as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" width="24" height="24">'
            '<rect x="3" y="3" width="18" height="18" rx="2"/>'
            '<path d="M9 9h6v6H9z"/>'
            '</svg>\n'
        )

    with open(f"{name}/requirements.txt", "w") as f:
        f.write("imperal-sdk>=5.0.0\n")

    with open(f"{name}/tests/__init__.py", "w") as f:
        pass

    test_content = (
        f'"""Tests for {name} extension."""\n'
        f'import pytest\n'
        f'from imperal_sdk.testing import MockContext\n'
        f'from main import ext\n'
    )
    if template == "chat":
        test_content += (
            f'from main import GreetParams, fn_greet\n\n\n'
            f'def test_extension_registered():\n'
            f'    assert ext.app_id == "{app_id}"\n'
            f'    assert ext.version == "1.0.0"\n'
            f'    assert ext.display_name and ext.display_name != ext.app_id\n'
            f'    assert len(ext.description) >= 40\n\n\n'
            f'@pytest.mark.asyncio\n'
            f'async def test_greet_returns_action_result():\n'
            f'    ctx = MockContext(user_id="imp_u_test")\n'
            f'    result = await fn_greet(ctx, GreetParams(name="Alex"))\n'
            f'    assert result.status == "success"\n'
            f'    assert "Alex" in result.summary\n'
        )
    else:
        test_content += (
            f'\n\ndef test_extension_registered():\n'
            f'    assert ext.app_id == "{app_id}"\n'
            f'    assert ext.version == "1.0.0"\n'
            f'    assert "{ident}" in ext.tools\n'
        )

    with open(f"{name}/tests/test_main.py", "w") as f:
        f.write(test_content)

    # NOTE: imperal.json must NOT be ignored. The deploy server clones the git
    # repository and reads the manifest from the checkout, so a scaffold that
    # gitignores it produces a repo that builds and validates cleanly on the
    # developer's machine and then fails deploy with "imperal.json not found" —
    # which every new developer hit on their very first deploy.
    with open(f"{name}/.gitignore", "w") as f:
        f.write(
            "venv/\n.venv/\n__pycache__/\n*.pyc\n*.pyo\n.pytest_cache/\n"
            ".env\n.imperal/\n.DS_Store\n"
        )

    click.echo(f"Extension '{name}' scaffolded (template: {template})")
    click.echo(f"")
    click.echo(f"Next steps:")
    click.echo(f"  cd {name}")
    click.echo(f"  pip install 'imperal-sdk>=5.0.0'")
    click.echo(f"  imperal build       # generates imperal.json")
    click.echo(f"  imperal validate    # runs V1-V24+V31 federal validators")
    click.echo(f"  imperal test        # smoke-test handlers via MockContext")
    click.echo(f"  imperal deploy      # upload to panel.imperal.io/developer")


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
    """Validate extension against the current SDK federal rules (V1-V24+V31)."""
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
        report = validate_extension(ext)

        # v1.6.0 AST rules (SKEL-GUARD-*, CACHE-MODEL-1, CACHE-TTL-1,
        # MANIFEST-SKELETON-1) — source-level, independent of ext instance.
        source_root = os.getcwd()
        for issue in validate_source_tree(source_root):
            report.issues.append(issue)

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

        click.echo(f"\n── Imperal Extension Validator (SDK {SDK_VERSION}) {'─' * 36}")
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
    # sys.executable, not "python": modern macOS and most Linux distros ship
    # only python3, so the hard-coded name fails with "python: command not
    # found". This also guarantees the tests run in the SAME interpreter (and
    # virtualenv) that is running imperal itself.
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"])
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
@click.option("--limit", default=10, show_default=True,
              help="How many deploy records to show (1-20).")
def logs(limit: int):
    """Show this extension's recent deploy history and how to read its logs.

    Until 2026-08-15 this command printed "Connecting to Imperal Cloud logs..."
    followed by "(Not yet implemented — will stream from SigNoz)" — the whole
    command was a stub, so the one obvious place a developer looks after a
    failed deploy told them nothing at all.

    Live log STREAMING still does not exist: there is no log-collection endpoint
    to stream from (the platform workers export traces to SigNoz, not logs), and
    ctx.log() writes to the worker's own process log. Rather than keep promising
    a pipeline that is not there, this now prints the diagnostic record the
    platform DOES keep per app — deploy attempts with status, commit and error
    message — and says plainly where the rest lives.
    """
    sys.path.insert(0, ".")
    try:
        from main import ext
    except ImportError:
        click.echo("Error: No main.py found. Run this inside an extension "
                   "directory.", err=True)
        raise SystemExit(1)

    limit = max(1, min(int(limit), 20))
    creds = _load_credentials()
    gateway = (creds.get("gateway_url") or "").rstrip("/")

    if not gateway or not creds.get("api_key"):
        click.echo("No gateway credentials configured — cannot read deploy "
                   "history.")
        click.echo("Set gateway_url + api_key in .imperal/credentials "
                   "(or IMPERAL_GATEWAY_URL / IMPERAL_API_KEY).")
        raise SystemExit(1)

    click.echo(f"Deploy history for {ext.app_id} (most recent first):\n")
    try:
        resp = httpx.get(
            f"{gateway}/v1/developer/apps/{ext.app_id}/deploys",
            headers={"x-api-key": creds["api_key"]},
            timeout=15,
        )
        resp.raise_for_status()
        records = resp.json() or []
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 404:
            click.echo(f"  App {ext.app_id!r} not found on the platform — "
                       f"deploy it first (imperal deploy).")
        elif code in (401, 403):
            click.echo("  Credentials rejected — check api_key in "
                       ".imperal/credentials.")
        else:
            click.echo(f"  Could not read deploy history (HTTP {code}).")
        raise SystemExit(1)
    except httpx.HTTPError as e:
        click.echo(f"  Could not reach the gateway: {e}")
        raise SystemExit(1)

    if not records:
        click.echo("  No deploys recorded yet.")
    for r in records[:limit]:
        status = (r.get("status") or "unknown").upper()
        when = r.get("deployed_at") or "?"
        sha = (r.get("commit_sha") or "")[:8] or "-"
        click.echo(f"  {when}  {status:<8} {sha}")
        err = r.get("error_message")
        if err:
            click.echo(f"      └─ {err}")

    click.echo(
        "\nRuntime logs are not streamable from here yet.\n"
        "  • ctx.log() lands in the platform worker's process log — ask an\n"
        "    operator for `journalctl -u imperal-platform-worker@1`, filtered\n"
        f"    on the logger name ext.{ext.app_id}\n"
        "  • per-tool call outcomes are recorded in the platform audit trail\n"
        "  • scheduled runs: see `imperal schedules`"
    )


@cli.command()
def schedules():
    """List this extension's scheduled tasks and their next fire times.

    A scheduled task previously had NO status surface at all: nothing in the CLI
    reported which schedules exist, when they last ran, or when they run next —
    so a cron that never fired looked identical to one that fired and did
    nothing (platform sweep #29).

    Last-run history is per-fire audit data the platform records centrally and
    does not expose to app authors, so it is honestly not shown here. What this
    DOES give you is the part that is knowable locally and was missing: the
    registered schedules, their cron expressions, and the next times each one
    will fire — enough to tell "my cron is not registered" apart from "my cron
    is registered and its body is not doing what I expect".
    """
    sys.path.insert(0, ".")
    try:
        from main import ext
    except ImportError:
        click.echo("Error: No main.py found. Run this inside an extension "
                   "directory.", err=True)
        raise SystemExit(1)

    scheds = getattr(ext, "schedules", {}) or {}
    if not scheds:
        click.echo(f"{ext.app_id}: no scheduled tasks registered.")
        click.echo("Add one with @ext.schedule(\"name\", cron=\"*/5 * * * *\").")
        return

    click.echo(f"{ext.app_id}: {len(scheds)} scheduled task(s)\n")
    for name, sd in scheds.items():
        cron = getattr(sd, "cron", "?")
        click.echo(f"  {name}")
        click.echo(f"    cron: {cron}  (UTC, minute resolution)")
        for line in _describe_next_fires(cron):
            click.echo(f"    {line}")

    click.echo(
        "\nA scheduled task runs in SYSTEM context: ctx.user.imperal_id is\n"
        "\"__system__\" and ctx.store sees the system's own rows, NOT your\n"
        "users'. Fan out with ctx.store.list_users(<collection>) +\n"
        "ctx.as_user(uid) — see help(ext.schedule)."
    )


def _describe_next_fires(cron: str, count: int = 3) -> list[str]:
    """Return human lines for the next `count` UTC fire times of a 5-field cron.

    Deliberately dependency-free: the SDK must not grow a cron library just to
    print three timestamps. Scans forward minute by minute over a bounded
    window and reports honestly if it finds nothing in range.
    """
    from datetime import datetime, timedelta, timezone

    fields = (cron or "").split()
    if len(fields) != 5:
        return [f"next: cannot parse cron {cron!r} (expected 5 fields)"]

    def matches(field: str, value: int, lo: int, hi: int) -> bool:
        for part in field.split(","):
            if part == "*":
                return True
            step = 1
            if "/" in part:
                part, _, raw_step = part.partition("/")
                if not raw_step.isdigit() or int(raw_step) == 0:
                    return False
                step = int(raw_step)
            if part == "*":
                start, end = lo, hi
            elif "-" in part:
                a, _, b = part.partition("-")
                if not (a.isdigit() and b.isdigit()):
                    return False
                start, end = int(a), int(b)
            elif part.isdigit():
                start = end = int(part)
                if step == 1:
                    if value == start:
                        return True
                    continue
            else:
                return False
            if start <= value <= end and (value - start) % step == 0:
                return True
        return False

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    found: list[str] = []
    probe = now + timedelta(minutes=1)
    # 8 days covers every weekly schedule; monthly ones are reported as such.
    for _ in range(8 * 24 * 60):
        if (matches(fields[0], probe.minute, 0, 59)
                and matches(fields[1], probe.hour, 0, 23)
                and matches(fields[2], probe.day, 1, 31)
                and matches(fields[3], probe.month, 1, 12)
                and matches(fields[4], probe.weekday() + 1 if probe.weekday() < 6 else 0, 0, 6)):
            delta = probe - now
            mins = int(delta.total_seconds() // 60)
            when = f"in {mins}m" if mins < 60 else f"in {mins // 60}h{mins % 60:02d}m"
            found.append(f"next: {probe.strftime('%Y-%m-%d %H:%M')} UTC ({when})")
            if len(found) >= count:
                break
        probe += timedelta(minutes=1)

    if not found:
        return ["next: no fire time within the next 8 days "
                "(monthly/yearly schedule, or an expression that never matches)"]
    return found


if __name__ == "__main__":
    cli()
