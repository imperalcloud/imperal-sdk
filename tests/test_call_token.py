import pytest

from imperal_sdk.security.call_token import (
    CallTokenError,
    mint_call_token,
    verify_call_token,
    verify_call_token_any_tool_type,
)


SECRET = b"test-secret-32-bytes-urlsafe-base64-for-unit-tests-only"


class FakeRedis:
    def __init__(self):
        self._store = {}
    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True


def test_mint_and_verify_roundtrip():
    token = mint_call_token(
        tool_type="skeleton",
        app_id="mail",
        user_id="u-123",
        ttl_seconds=120,
        hmac_secret=SECRET,
    )
    assert isinstance(token, str)
    assert "." in token


@pytest.mark.asyncio
async def test_verify_accepts_correct_token():
    token = mint_call_token("skeleton", "mail", "u-123", 120, SECRET)
    r = FakeRedis()
    await verify_call_token(
        token,
        required_tool_type="skeleton",
        required_app_id="mail",
        required_user_id="u-123",
        hmac_secrets=[SECRET],
        redis=r,
    )


@pytest.mark.asyncio
async def test_verify_rejects_tampered_signature():
    token = mint_call_token("skeleton", "mail", "u-123", 120, SECRET)
    payload, sig = token.split(".")
    # Pick a tamper char that is GUARANTEED to differ from sig[0] —
    # avoids 1/64 flake where sig[0] happens to equal hardcoded "X".
    tamper_char = "Y" if sig[0] != "Y" else "Z"
    tampered = payload + "." + tamper_char + sig[1:]
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="signature"):
        await verify_call_token(
            tampered, "skeleton", "mail", "u-123", [SECRET], r
        )


@pytest.mark.asyncio
async def test_verify_rejects_tool_type_mismatch():
    token = mint_call_token("panel", "mail", "u-123", 120, SECRET)
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="tool_type"):
        await verify_call_token(
            token, "skeleton", "mail", "u-123", [SECRET], r
        )


@pytest.mark.asyncio
async def test_verify_rejects_app_id_mismatch():
    token = mint_call_token("skeleton", "mail", "u-123", 120, SECRET)
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="app_id"):
        await verify_call_token(
            token, "skeleton", "sharelock-v2", "u-123", [SECRET], r
        )


@pytest.mark.asyncio
async def test_verify_rejects_user_id_mismatch():
    token = mint_call_token("skeleton", "mail", "u-123", 120, SECRET)
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="user_id"):
        await verify_call_token(
            token, "skeleton", "mail", "u-999", [SECRET], r
        )


@pytest.mark.asyncio
async def test_verify_rejects_expired_token():
    token = mint_call_token("skeleton", "mail", "u-123", -1, SECRET)
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="expired"):
        await verify_call_token(
            token, "skeleton", "mail", "u-123", [SECRET], r
        )


@pytest.mark.asyncio
async def test_verify_rejects_replay():
    token = mint_call_token("skeleton", "mail", "u-123", 120, SECRET)
    r = FakeRedis()
    await verify_call_token(token, "skeleton", "mail", "u-123", [SECRET], r)
    with pytest.raises(CallTokenError, match="replayed"):
        await verify_call_token(token, "skeleton", "mail", "u-123", [SECRET], r)


@pytest.mark.asyncio
async def test_verify_rotation_accepts_second_secret():
    NEW_SECRET = b"new-secret-for-rotation-test-32-bytes-content-here"
    token = mint_call_token("skeleton", "mail", "u-123", 120, SECRET)
    r = FakeRedis()
    await verify_call_token(
        token, "skeleton", "mail", "u-123", [NEW_SECRET, SECRET], r
    )


@pytest.mark.asyncio
async def test_any_tool_type_accepts_all_four():
    for tool_type in ("skeleton", "panel", "tool", "chat_fn"):
        token = mint_call_token(tool_type, "mail", "u-123", 120, SECRET)
        r = FakeRedis()
        await verify_call_token_any_tool_type(
            token, "mail", "u-123", [SECRET], r
        )


@pytest.mark.asyncio
async def test_malformed_token_rejected():
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="malformed"):
        await verify_call_token(
            "not-a-token", "skeleton", "mail", "u-123", [SECRET], r
        )


@pytest.mark.asyncio
async def test_verify_rejects_empty_string_token():
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="malformed"):
        await verify_call_token("", "skeleton", "mail", "u-1", [SECRET], r)


@pytest.mark.asyncio
async def test_verify_rejects_empty_hmac_secrets_list():
    token = mint_call_token("skeleton", "mail", "u-1", 120, SECRET)
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="signature"):
        await verify_call_token(token, "skeleton", "mail", "u-1", [], r)


@pytest.mark.asyncio
async def test_verify_rejects_oversized_token():
    r = FakeRedis()
    oversized = "a" * 5000 + "." + "b" * 5000
    with pytest.raises(CallTokenError, match="length"):
        await verify_call_token(oversized, "skeleton", "mail", "u-1", [SECRET], r)


@pytest.mark.asyncio
async def test_verify_rejects_valid_sig_over_invalid_json():
    # Build a token manually where signature is valid over bytes that aren't
    # valid JSON.
    import base64
    import hmac as _hmac
    import hashlib as _hashlib
    payload = b"not-json-garbage"
    sig = _hmac.new(SECRET, payload, _hashlib.sha256).digest()
    token = (
        base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    )
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="payload"):
        await verify_call_token(token, "skeleton", "mail", "u-1", [SECRET], r)


@pytest.mark.asyncio
async def test_verify_rejects_missing_claims():
    # Valid sig, valid JSON, but missing required fields.
    import base64
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    payload = _json.dumps({"tool_type": "skeleton"}).encode()
    sig = _hmac.new(SECRET, payload, _hashlib.sha256).digest()
    token = (
        base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        + "."
        + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    )
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="payload"):
        await verify_call_token(token, "skeleton", "mail", "u-1", [SECRET], r)


@pytest.mark.asyncio
async def test_verify_rejects_exact_boundary_expiry():
    """RFC 7519 § 4.1.4: current time MUST be BEFORE expiration — equal ⇒ expired."""
    token = mint_call_token("skeleton", "mail", "u-1", 0, SECRET)
    r = FakeRedis()
    with pytest.raises(CallTokenError, match="expired"):
        await verify_call_token(token, "skeleton", "mail", "u-1", [SECRET], r)
