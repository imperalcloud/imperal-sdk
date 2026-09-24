# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""ICNLI Manifest Smart Linter & Auto-Fixer.

Guides developers through imperal.json validation with actionable diagnostics,
explanation of platform invariants, and automated fixing of schema boilerplate
(missing search_providers, category defaults, scopes formatting, schema versions).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


class ManifestLinter:
    """Intelligent linter and fixer for imperal.json manifests."""

    LATEST_SCHEMA_VERSION = "1.6.0"
    DEFAULT_CATEGORY = "productivity"

    @classmethod
    def lint_dict(cls, manifest: Dict[str, Any], fix: bool = False) -> Tuple[List[str], List[str], Dict[str, Any]]:
        """Lint a parsed manifest dictionary.

        Returns:
            (errors, warnings, potentially_fixed_manifest)
        """
        errors: List[str] = []
        warnings: List[str] = []
        data = dict(manifest)

        # 1. Essential metadata
        for field in ("app_id", "name", "version", "description"):
            if not data.get(field):
                errors.append(f"Missing required field '{field}' in manifest.")

        # 2. Schema version check & auto-upgrade
        schema_v = data.get("schema_version")
        if not schema_v:
            if fix:
                data["schema_version"] = cls.LATEST_SCHEMA_VERSION
                warnings.append(f"[FIXED] Injected 'schema_version': '{cls.LATEST_SCHEMA_VERSION}'.")
            else:
                warnings.append(f"Missing 'schema_version' (recommended: '{cls.LATEST_SCHEMA_VERSION}').")
        elif schema_v != cls.LATEST_SCHEMA_VERSION and fix:
            data["schema_version"] = cls.LATEST_SCHEMA_VERSION
            warnings.append(f"[FIXED] Upgraded 'schema_version' to '{cls.LATEST_SCHEMA_VERSION}'.")

        # 3. Category
        if not data.get("category"):
            if fix:
                data["category"] = cls.DEFAULT_CATEGORY
                warnings.append(f"[FIXED] Set default category: '{cls.DEFAULT_CATEGORY}'.")
            else:
                warnings.append("Missing 'category'.")

        # 4. Search Providers (5.15.1+ requirement)
        if "search_providers" not in data:
            if fix:
                data["search_providers"] = []
                warnings.append("[FIXED] Added missing 'search_providers: []' list.")
            else:
                warnings.append("Manifest does not declare 'search_providers' (expected list).")

        # 5. Secrets validation
        secrets = data.get("secrets", [])
        if not isinstance(secrets, list):
            errors.append("'secrets' must be a list of secret declarations.")
        else:
            for idx, sec in enumerate(secrets):
                if isinstance(sec, str):
                    if fix:
                        # Auto-convert string secret to structured object
                        secrets[idx] = {"name": sec, "description": f"{sec} secret credential", "required": True}
                        warnings.append(f"[FIXED] Converted secret '{sec}' to structured declaration.")
                elif isinstance(sec, dict) and "name" not in sec:
                    errors.append(f"Secret item #{idx} is missing 'name'.")

        # 6. Scopes validation
        scopes = data.get("scopes", [])
        if not isinstance(scopes, list):
            errors.append("'scopes' must be a list.")

        # 7. Handlers / Functions validation
        functions = data.get("functions", [])
        if not isinstance(functions, list):
            errors.append("'functions' must be a list of registered tools.")
        else:
            for fn in functions:
                if isinstance(fn, dict):
                    fn_name = fn.get("name")
                    if not fn_name:
                        errors.append("Function declaration missing 'name'.")
                    if "risk_level" not in fn and fix:
                        fn["risk_level"] = "read"
                        warnings.append(f"[FIXED] Injected default 'risk_level: read' for function '{fn_name}'.")

        return errors, warnings, data

    @classmethod
    def lint_file(cls, path: Path | str, fix: bool = False) -> Tuple[List[str], List[str], bool]:
        """Lint and optionally fix a manifest file in place.

        Returns:
            (errors, warnings, was_file_modified)
        """
        p = Path(path)
        if not p.exists():
            return [f"File not found: {p}"], [], False

        try:
            content = p.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as exc:
            return [f"Failed to parse JSON: {exc}"], [], False

        errors, warnings, fixed_data = cls.lint_dict(data, fix=fix)
        modified = False
        if fix and fixed_data != data:
            p.write_text(json.dumps(fixed_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            modified = True

        return errors, warnings, modified
