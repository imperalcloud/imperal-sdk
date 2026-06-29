import pytest
from imperal_sdk.secrets.spec import SecretSpec, ALLOWED_SCOPES


def test_scope_defaults_to_user():
    s = SecretSpec(name="refresh_token", description="user token")
    assert s.scope == "user"
    assert s.to_manifest_dict()["scope"] == "user"


def test_app_scope_in_manifest_with_env_fallback():
    s = SecretSpec(
        name="google_client_secret",
        description="Google OAuth client secret (shared).",
        scope="app",
        env_fallback="IMPERAL_APPSECRET_MAIL_GOOGLE_CLIENT_SECRET",
    )
    d = s.to_manifest_dict()
    assert d["scope"] == "app"
    assert d["env_fallback"] == "IMPERAL_APPSECRET_MAIL_GOOGLE_CLIENT_SECRET"


def test_env_fallback_must_be_namespaced():
    with pytest.raises(ValueError):
        SecretSpec(name="x_key", description="d", scope="app", env_fallback="STRIPE_SECRET_KEY")


def test_env_fallback_requires_app_scope():
    with pytest.raises(ValueError):
        SecretSpec(name="x_key", description="d", env_fallback="IMPERAL_APPSECRET_X_KEY")


def test_invalid_scope_rejected():
    with pytest.raises(ValueError):
        SecretSpec(name="x_key", description="d", scope="global")


def test_allowed_scopes_value():
    assert ALLOWED_SCOPES == frozenset({"user", "app"})
