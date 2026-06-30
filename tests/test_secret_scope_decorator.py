# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""ext.secret(scope=..., env_fallback=...) must reach SecretSpec + the manifest.

Regression: 5.8.0 added SecretSpec.scope/env_fallback + manifest emission but the
ext.secret() decorator never forwarded them, so ext.secret(scope="app") raised
TypeError and app-scope secrets could not be declared from code (the documented way)."""
from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest


def test_secret_accepts_and_emits_scope_app():
    ext = Extension("mail", version="1.0.0")
    ext.secret(name="google_client_id", description="shared OAuth client id",
               scope="app")(lambda: None)
    decl = [s for s in generate_manifest(ext)["secrets"] if s["name"] == "google_client_id"][0]
    assert decl["scope"] == "app"


def test_secret_forwards_env_fallback():
    ext = Extension("mail", version="1.0.0")
    ext.secret(name="google_client_secret", description="shared OAuth client secret",
               scope="app", env_fallback="IMPERAL_APPSECRET_MAIL_GOOGLE_CLIENT_SECRET")(lambda: None)
    decl = [s for s in generate_manifest(ext)["secrets"] if s["name"] == "google_client_secret"][0]
    assert decl["scope"] == "app"
    assert decl["env_fallback"] == "IMPERAL_APPSECRET_MAIL_GOOGLE_CLIENT_SECRET"


def test_secret_scope_defaults_to_user():
    ext = Extension("notes", version="1.0.0")
    ext.secret(name="api_key", description="user key")(lambda: None)
    decl = [s for s in generate_manifest(ext)["secrets"] if s["name"] == "api_key"][0]
    assert decl["scope"] == "user"
