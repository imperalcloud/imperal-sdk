# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Tests for imperal sdk CLI commands: init, validate, and --fix."""
import json
import os
from click.testing import CliRunner
from imperal_sdk.cli.main import cli


def test_sdk_init_command(tmp_path):
    runner = CliRunner()
    target = str(tmp_path / "scaffold_app")
    result = runner.invoke(cli, ["sdk", "init", target])
    assert result.exit_code == 0
    assert os.path.exists(os.path.join(target, "main.py"))
    assert os.path.exists(os.path.join(target, "icon.svg"))


def test_sdk_validate_fix_command(tmp_path):
    runner = CliRunner()
    app_dir = tmp_path / "fixable_app"
    app_dir.mkdir()
    manifest = app_dir / "imperal.json"
    manifest.write_text(json.dumps({
        "app_id": "fixable_app",
        "name": "Fixable App",
        "version": "1.0.0",
        "description": "A valid long description that satisfies the minimum length requirement.",
    }))
    
    # Run sdk validate --fix
    result = runner.invoke(cli, ["sdk", "validate", str(app_dir), "--fix"])
    # Validation will try to import main.py, but verify --fix ran on manifest
    updated = json.loads(manifest.read_text())
    assert updated.get("schema_version") == "1.6.0"
    assert "search_providers" in updated
    assert updated.get("category") == "productivity"
