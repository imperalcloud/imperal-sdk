# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Task E6: Full-app mapping proof — automations ext → IR, no rewrite.

Approach: live-ext import via `main.py` (not `app.py` alone).
Rationale: `app.py` only declares the Extension object; tool decorators
(@chat.function, @ext.skeleton, @ext.panel) live in handlers.py / skeleton.py /
panels.py / panels_center.py and are registered when those modules are imported.
`main.py` is the canonical loader that imports all sub-modules — it is the
correct entry point to get a fully-populated Extension.

The test imports `main` (not `app`) and grabs `main.ext`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from imperal_sdk.ir.produce import generate_ir
from imperal_sdk.ir.validator import validate_ir_dict

AUTOMATIONS = Path("/Users/val-mac/Nextcloud/MCP-Configs/imperal-ext-automations")

_reason_missing = "imperal-ext-automations directory not present"


@pytest.mark.skipif(not AUTOMATIONS.exists(), reason=_reason_missing)
def test_automations_ext_maps_to_valid_ir():
    """Importing the real automations ext via main.py and running generate_ir
    must produce a valid IR with no errors (success criterion #7)."""
    if str(AUTOMATIONS) not in sys.path:
        sys.path.insert(0, str(AUTOMATIONS))

    # main.py is the canonical loader: imports app → handlers → skeleton →
    # panels → panels_center, registering all tools on ext.
    main = importlib.import_module("main")
    ext = main.ext

    ir = generate_ir(ext)

    # Core validity
    assert validate_ir_dict(ir) == [], "IR must pass schema validation with no errors"

    app = ir["app"]
    assert app["id"] == "automations", "app.id must be 'automations'"
    assert app["version"], "app.version must be non-empty"

    # Functions slot — automations registers list/create/update/delete/etc.
    functions = app["functions"]
    assert functions, "IR must contain at least one function"
    assert all(
        f["impl"]["kind"] == "code" for f in functions
    ), "All functions must have impl.kind=='code'"

    # Check expected automations functions are present
    fn_names = {f["name"] for f in functions}
    assert "list_automations" in fn_names, "list_automations must be in IR functions"

    # UI slot — automations has sidebar (left) + workshop (center) panels
    ui = app.get("ui")
    assert ui is not None, "IR must contain a ui slot (automations has 2 panels)"
    panels = ui.get("panels", [])
    assert len(panels) >= 1, "IR ui must contain at least one panel"
    panel_ids = {p["panel_id"] for p in panels}
    assert "sidebar" in panel_ids, "sidebar panel must be present in IR ui"

    # Skeleton slot — automations registers skeleton_refresh_rules
    skeleton = app.get("skeleton")
    assert skeleton, "IR must contain a skeleton slot (automations has skeleton_refresh_rules)"
    sections = {s["section"] for s in skeleton}
    assert "rules" in sections, "skeleton section 'rules' must be present"
