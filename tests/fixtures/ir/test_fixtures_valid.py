import json
import pathlib

import pytest

from imperal_sdk.ir.validator import validate_ir_dict
from imperal_sdk.ir.actions import validate_step

FIX = pathlib.Path(__file__).parent


@pytest.mark.parametrize("name", ["link_saver", "archive_ended"])
def test_fixture_is_valid_declarative(name):
    ir = json.loads((FIX / f"{name}.ir.json").read_text())
    assert validate_ir_dict(ir) == [], f"{name}: envelope invalid"
    for fn in ir["app"]["functions"]:
        assert fn["impl"]["kind"] == "declarative", f"{name}/{fn['name']}: not declarative"
        for step in fn["impl"].get("steps", []):
            assert validate_step(step) == [], (name, fn["name"], step.get("op"), validate_step(step))
