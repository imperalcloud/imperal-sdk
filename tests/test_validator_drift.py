"""W1 — Identity contract drift validator tests.

Verifies imperal_sdk.tools.validate_identity_contract correctly:
- Detects field-set mismatches between SDK Pydantic and SQLAlchemy DB columns
- Honors EXCLUDED_FROM_API allowlist (password_hash, id, db_config)
- Verifies subset invariants (UserContext ⊂ User, TenantContext ⊂ Tenant)
"""
import pytest


# Raw SQLAlchemy fixtures — 4-space indent, no dedent dance.
_ALIGNED_USER_PY = """from sqlalchemy.orm import Mapped, mapped_column
class User(Base):
    id: Mapped[str] = mapped_column(String(36))
    imperal_id: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(255))
    agency_id: Mapped[str | None] = mapped_column(String(50))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    tenant_id: Mapped[str] = mapped_column(String(63))
    org_id: Mapped[str | None] = mapped_column(String(63))
    role: Mapped[str] = mapped_column(String(20))
    auth_method: Mapped[str] = mapped_column(String(20))
    scopes: Mapped[dict] = mapped_column(JSON)
    attributes: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    cases_user_id: Mapped[int | None] = mapped_column(Integer)
"""


_ALIGNED_TENANT_PY = """from sqlalchemy.orm import Mapped, mapped_column
class Tenant(Base):
    id: Mapped[str] = mapped_column(String(36))
    tenant_id: Mapped[str] = mapped_column(String(63))
    name: Mapped[str] = mapped_column(String(255))
    db_backend: Mapped[str] = mapped_column(String(20))
    db_config: Mapped[str] = mapped_column(Text)
    isolation: Mapped[str] = mapped_column(String(20))
    allowed_auth_methods: Mapped[str] = mapped_column(String(255))
    max_connections: Mapped[int] = mapped_column(Integer)
    features: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    parent_tenant_id: Mapped[str | None] = mapped_column(String(63))
    can_resell: Mapped[bool] = mapped_column(Boolean)
    custom_pricing: Mapped[dict] = mapped_column(JSON)
    ui_config: Mapped[dict] = mapped_column(JSON)
"""


def test_validator_passes_aligned_user_schema(tmp_path):
    from imperal_sdk.tools.validate_identity_contract import validate_user_against_db
    p = tmp_path / "user.py"
    p.write_text(_ALIGNED_USER_PY)
    errors = validate_user_against_db(str(p))
    assert errors == [], f"Expected aligned schema, got: {errors}"


def test_validator_passes_aligned_tenant_schema(tmp_path):
    from imperal_sdk.tools.validate_identity_contract import validate_tenant_against_db
    p = tmp_path / "tenant.py"
    p.write_text(_ALIGNED_TENANT_PY)
    errors = validate_tenant_against_db(str(p))
    assert errors == [], f"Expected aligned schema, got: {errors}"


def test_validator_catches_extra_field_in_db(tmp_path):
    from imperal_sdk.tools.validate_identity_contract import validate_user_against_db
    drifted = _ALIGNED_USER_PY.replace(
        "    is_active: Mapped[bool] = mapped_column(Boolean)\n",
        "    is_active: Mapped[bool] = mapped_column(Boolean)\n"
        "    new_admin_field: Mapped[str] = mapped_column(String(50))\n",
    )
    p = tmp_path / "user.py"
    p.write_text(drifted)
    errors = validate_user_against_db(str(p))
    assert any("new_admin_field" in e for e in errors), f"Expected drift, got: {errors}"


def test_validator_catches_missing_field_in_db(tmp_path):
    from imperal_sdk.tools.validate_identity_contract import validate_user_against_db
    drifted = _ALIGNED_USER_PY.replace(
        "    cases_user_id: Mapped[int | None] = mapped_column(Integer)\n",
        "",
    )
    p = tmp_path / "user.py"
    p.write_text(drifted)
    errors = validate_user_against_db(str(p))
    assert any("cases_user_id" in e for e in errors), f"Expected missing-in-DB drift, got: {errors}"


def test_validator_excludes_password_hash_and_id():
    from imperal_sdk.tools.validate_identity_contract import EXCLUDED_FROM_API
    assert "password_hash" in EXCLUDED_FROM_API["User"]
    assert "id" in EXCLUDED_FROM_API["User"]
    assert "db_config" in EXCLUDED_FROM_API["Tenant"]


def test_validator_subset_invariant_passes_currently():
    from imperal_sdk.tools.validate_identity_contract import validate_subset_invariants
    errors = validate_subset_invariants()
    assert errors == [], f"Subset invariants must hold: {errors}"
