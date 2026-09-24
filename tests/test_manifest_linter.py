# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Tests for ManifestLinter and smart --fix capability."""
from pathlib import Path
from imperal_sdk.cli.linter import ManifestLinter


def test_manifest_linter_detects_missing_fields():
    broken = {
        "app_id": "test_app",
        "name": "Test App",
    }
    errors, warnings, _ = ManifestLinter.lint_dict(broken, fix=False)
    assert any("version" in e for e in errors)
    assert any("description" in e for e in errors)
    assert any("search_providers" in w for w in warnings)


def test_manifest_linter_auto_fix():
    manifest = {
        "app_id": "my_extension",
        "name": "My Extension",
        "version": "1.0.0",
        "description": "Awesome tool",
        "secrets": ["API_KEY"],
        "functions": [{"name": "do_work"}],
    }
    errors, warnings, fixed = ManifestLinter.lint_dict(manifest, fix=True)
    assert errors == []
    # Auto-injected schema_version
    assert fixed["schema_version"] == "1.6.0"
    # Auto-injected category
    assert fixed["category"] == "productivity"
    # Auto-injected search_providers
    assert fixed["search_providers"] == []
    # Structured secret
    assert isinstance(fixed["secrets"][0], dict)
    assert fixed["secrets"][0]["name"] == "API_KEY"
    # Default risk_level
    assert fixed["functions"][0]["risk_level"] == "read"
    assert any("[FIXED]" in w for w in warnings)


def test_manifest_linter_file_io(tmp_path: Path):
    f = tmp_path / "imperal.json"
    f.write_text('{"app_id": "t", "name": "T", "version": "1.0.0", "description": "D"}')

    errors, warnings, modified = ManifestLinter.lint_file(f, fix=True)
    assert errors == []
    assert modified is True
    assert "schema_version" in f.read_text()
    assert "search_providers" in f.read_text()
