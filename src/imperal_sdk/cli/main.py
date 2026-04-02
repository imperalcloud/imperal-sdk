# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Imperal Cloud SDK CLI."""
import os
import click


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Imperal Cloud SDK — build extensions for the Imperal platform."""
    pass


@cli.command()
@click.argument("name")
def init(name: str):
    """Scaffold a new extension project."""
    os.makedirs(name, exist_ok=True)
    os.makedirs(f"{name}/tests", exist_ok=True)

    with open(f"{name}/main.py", "w") as f:
        f.write(f'''from imperal_sdk import Extension

ext = Extension("{name}", version="0.1.0")


@ext.tool("hello", description="Say hello")
async def hello(ctx, name: str = "World"):
    """Say hello."""
    return {{"message": f"Hello, {{name}}!"}}
''')

    with open(f"{name}/requirements.txt", "w") as f:
        f.write("imperal-sdk>=0.1.0\n")

    with open(f"{name}/tests/__init__.py", "w") as f:
        pass

    with open(f"{name}/tests/test_hello.py", "w") as f:
        f.write(f'''import pytest
from main import ext


def test_hello_tool_registered():
    assert "hello" in ext.tools


@pytest.mark.asyncio
async def test_hello_tool():
    result = await ext.call_tool("hello", ctx=None, name="Imperal")
    assert result == {{"message": "Hello, Imperal!"}}
''')

    with open(f"{name}/.gitignore", "w") as f:
        f.write("venv/\n__pycache__/\n*.pyc\n.env\nmanifest.json\n")

    click.echo(f"Extension '{name}' created!")
    click.echo(f"  cd {name}")
    click.echo(f"  pip install imperal-sdk")
    click.echo(f"  imperal dev")


@cli.command()
def dev():
    """Run local development server with hot reload."""
    import sys
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
def test():
    """Run extension tests."""
    import subprocess
    result = subprocess.run(["python", "-m", "pytest", "tests/", "-v"])
    raise SystemExit(result.returncode)


@cli.command()
def deploy():
    """Deploy extension to Imperal Cloud."""
    import sys
    sys.path.insert(0, ".")
    try:
        from main import ext
        from imperal_sdk.manifest import generate_manifest, save_manifest
        save_manifest(ext)
        click.echo(f"Manifest generated: manifest.json")
        click.echo(f"Extension: {ext.app_id} v{ext.version}")
        click.echo("Deploy to Imperal Cloud...")
        click.echo("(Not yet implemented — will push to Registry)")
    except ImportError:
        click.echo("Error: No main.py found.", err=True)
        raise SystemExit(1)


@cli.command()
def logs():
    """Tail production logs."""
    click.echo("Connecting to Imperal Cloud logs...")
    click.echo("(Not yet implemented — will stream from SigNoz)")


if __name__ == "__main__":
    cli()
