from imperal_sdk.ir.migrate import migrate_ir
from imperal_sdk.ir.validator import validate_ir_dict


def _ir():
    return {"ir_version": "1.0", "app": {"id": "a", "version": "1", "title": "A"}}


def test_identity_migration_is_noop():
    src = _ir()
    out = migrate_ir(src, to="1.0")
    assert out == src
    assert validate_ir_dict(out) == []


def test_unknown_target_raises():
    import pytest
    with pytest.raises(ValueError):
        migrate_ir(_ir(), to="9.9")
