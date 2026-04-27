"""W1 — User/Tenant identity contract tests.

Verifies canonical Pydantic types in imperal_sdk.types.identity:
- User (full, 13 fields, frozen, extra=forbid)
- UserContext (lean, strict subset of User)
- Tenant (full, 16 fields)
- TenantContext (lean, strict subset of Tenant)
- Import-time subset invariants
"""
import pytest
from pydantic import ValidationError


# ── User ──

def test_user_required_fields():
    from imperal_sdk.types.identity import User
    u = User(
        imperal_id="usr_abc123",
        email="user@example.com",
        tenant_id="default",
        role="user",
        auth_method="email",
        created_at="2026-04-27T08:00:00Z",
    )
    assert u.imperal_id == "usr_abc123"
    assert u.is_active is True  # default
    assert u.scopes == []
    assert u.attributes == {}
    assert u.agency_id is None
    assert u.last_login is None
    assert u.cases_user_id is None


def test_user_rejects_extra_fields():
    from imperal_sdk.types.identity import User
    with pytest.raises(ValidationError):
        User(
            imperal_id="usr_abc",
            email="u@e.com",
            tenant_id="default",
            role="user",
            auth_method="email",
            created_at="2026-04-27T08:00:00Z",
            password_hash="should-not-be-allowed",
        )


def test_user_is_frozen():
    from imperal_sdk.types.identity import User
    u = User(
        imperal_id="usr_a", email="u@e.com", tenant_id="t",
        role="user", auth_method="email", created_at="2026-04-27T08:00:00Z",
    )
    with pytest.raises(ValidationError):
        u.email = "other@e.com"


def test_user_serialization_roundtrip():
    from imperal_sdk.types.identity import User
    u1 = User(
        imperal_id="usr_x", email="x@y.com", tenant_id="t",
        role="user", auth_method="email", created_at="2026-04-27T08:00:00Z",
        scopes=["mail:read"], attributes={"k": "v"},
    )
    d = u1.model_dump()
    u2 = User.model_validate(d)
    assert u2 == u1


# ── UserContext ──

def test_user_context_lean():
    from imperal_sdk.types.identity import UserContext
    uc = UserContext(
        imperal_id="usr_abc",
        email="user@example.com",
        tenant_id="default",
        role="user",
    )
    assert uc.imperal_id == "usr_abc"
    assert uc.scopes == []
    assert uc.is_active is True


def test_user_context_strict_subset_of_user():
    from imperal_sdk.types.identity import User, UserContext
    user_fields = set(User.model_fields.keys())
    context_fields = set(UserContext.model_fields.keys())
    assert context_fields <= user_fields, (
        f"UserContext has fields not in User: {context_fields - user_fields}"
    )


def test_user_context_downcast_from_user_dict():
    """Kernel-side downcast pattern: full User dict → lean UserContext."""
    from imperal_sdk.types.identity import User, UserContext
    u = User(
        imperal_id="usr_a", email="a@b.c", tenant_id="t",
        role="user", auth_method="email", created_at="2026-04-27T08:00:00Z",
        last_login="2026-04-26T08:00:00Z", cases_user_id=42,
    )
    uc = UserContext.model_validate({
        k: v for k, v in u.model_dump().items()
        if k in UserContext.model_fields
    })
    assert uc.imperal_id == "usr_a"
    assert not hasattr(uc, "auth_method")
    assert not hasattr(uc, "last_login")
    assert not hasattr(uc, "cases_user_id")


# ── Tenant ──

def test_tenant_full_shape():
    from imperal_sdk.types.identity import Tenant
    t = Tenant(
        id="00000000-0000-0000-0000-000000000001",
        tenant_id="default",
        name="Default Tenant",
        db_backend="mariadb",
        isolation="shared",
        allowed_auth_methods="email,api_key",
        max_connections=10,
        created_at="2026-04-27T00:00:00Z",
        updated_at="2026-04-27T00:00:00Z",
    )
    assert t.tenant_id == "default"
    assert t.is_active is True
    assert t.features == {}
    assert t.parent_tenant_id is None


def test_tenant_rejects_db_config():
    """db_config holds secrets — never in canonical contract."""
    from imperal_sdk.types.identity import Tenant
    with pytest.raises(ValidationError):
        Tenant(
            id="x", tenant_id="t", name="T",
            db_backend="mariadb", isolation="shared",
            allowed_auth_methods="email", max_connections=10,
            created_at="x", updated_at="x",
            db_config="{secret_password: leaked}",
        )


# ── TenantContext ──

def test_tenant_context_lean():
    from imperal_sdk.types.identity import TenantContext
    tc = TenantContext(tenant_id="default", name="Default")
    assert tc.is_active is True
    assert tc.features == {}
    assert tc.isolation == "shared"


def test_tenant_context_strict_subset_of_tenant():
    from imperal_sdk.types.identity import Tenant, TenantContext
    assert set(TenantContext.model_fields.keys()) <= set(Tenant.model_fields.keys())


# ── Import-time invariants ──

def test_module_imports_with_invariants():
    """Import alone must not raise (subset invariants live at module load)."""
    import importlib
    import imperal_sdk.types.identity
    importlib.reload(imperal_sdk.types.identity)
