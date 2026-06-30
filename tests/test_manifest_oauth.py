# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""ext.oauth(...) declaration → manifest oauth[] emission + schema validation."""
from imperal_sdk import Extension
from imperal_sdk.manifest import generate_manifest
from imperal_sdk.manifest_schema import validate_manifest_dict


def test_oauth_declaration_emitted_and_valid():
    ext = Extension("mail", version="1.0.0")
    ext.oauth("google", collection="gmail_accounts",
              scopes=["https://www.googleapis.com/auth/gmail.modify"])
    m = generate_manifest(ext)
    assert m["oauth"] == [{
        "provider": "google",
        "collection": "gmail_accounts",
        "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
        "has_hook": False,
    }]
    assert validate_manifest_dict(m) == []


def test_no_oauth_section_when_none():
    ext = Extension("empty", version="1.0.0")
    assert "oauth" not in generate_manifest(ext)


def test_multiple_oauth_providers():
    ext = Extension("mail", version="1.0.0")
    ext.oauth("google", collection="gmail_accounts", scopes=["a"])
    ext.oauth("microsoft", collection="gmail_accounts", scopes=["b"])
    providers = {e["provider"] for e in generate_manifest(ext)["oauth"]}
    assert providers == {"google", "microsoft"}
