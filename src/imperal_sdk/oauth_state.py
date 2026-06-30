"""Signed OAuth `state` builder — MUST stay byte-for-byte compatible with the
gateway's app.oauth.state (same payload shape, same HMAC scheme, same key
resolution) so the gateway's verify_state accepts what the SDK signs.

Shared key: set ``IMPERAL_OAUTH_STATE_SECRET`` to the SAME value on the kernel
(where the SDK runs) and the gateway. Falls back through the call-token / service
secrets and finally a constant so dev/test round-trips work without extra env.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os


def _key() -> bytes:
    return (
        os.getenv("IMPERAL_OAUTH_STATE_SECRET")
        or os.getenv("IMPERAL_CALL_TOKEN_HMAC_SECRET")
        or os.getenv("IMPERAL_SERVICE_TOKEN")
        or "imperal-oauth-state-v1"
    ).encode()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def build_oauth_state(app_id: str, user_id: str, tenant_id: str, provider: str) -> str:
    payload = _b64e(json.dumps({
        "app_id": app_id, "user_id": user_id,
        "tenant_id": tenant_id, "provider": provider,
    }).encode())
    sig = _b64e(hmac.new(_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"
