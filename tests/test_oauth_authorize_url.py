# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""ctx.oauth_authorize_url — builds the provider authorize URL for the unified flow."""
import pytest

from imperal_sdk import Extension
from imperal_sdk.context import Context
from imperal_sdk.types.identity import UserContext


@pytest.fixture(autouse=True)
def _state_secret(monkeypatch):
    # build_oauth_state now requires a configured secret (no public fallback).
    monkeypatch.setenv("IMPERAL_OAUTH_STATE_SECRET", "test-state-secret")


class _FakeSecrets:
    async def get(self, name):
        return "CID123" if name.endswith("_client_id") else None


def _ctx_with_oauth():
    ext = Extension("mail", version="1.0.0")
    ext.oauth("google", collection="gmail_accounts",
              scopes=["https://www.googleapis.com/auth/gmail.modify"])
    user = UserContext(imperal_id="imp_u_X", email="", tenant_id="default",
                       role="user", scopes=[], attributes={})
    ctx = Context(user=user, tenant="default", _extension_id="mail", _extension=ext)
    ctx.secrets = _FakeSecrets()
    return ctx


async def test_authorize_url_has_all_components(monkeypatch):
    monkeypatch.setenv("IMPERAL_PUBLIC_HOST", "auth.imperal.io")
    url = await _ctx_with_oauth().oauth_authorize_url("google")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert ("redirect_uri=https%3A%2F%2Fauth.imperal.io%2Fv1%2Fext%2Fmail"
            "%2Foauth%2Fgoogle%2Fcallback") in url
    assert "client_id=CID123" in url
    assert "gmail.modify" in url
    assert "state=" in url
    assert "access_type=offline" in url


async def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        await _ctx_with_oauth().oauth_authorize_url("nope")
