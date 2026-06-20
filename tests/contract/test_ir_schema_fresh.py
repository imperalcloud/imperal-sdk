import json
from pathlib import Path
from imperal_sdk.ir.schema import get_ir_schema

SCHEMA = Path(__file__).resolve().parents[2] / "src" / "imperal_sdk" / "schemas" / "ir.schema.json"


def test_ir_schema_on_disk_matches_generator():
    on_disk = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert on_disk == get_ir_schema()
