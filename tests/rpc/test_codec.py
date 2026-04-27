"""Unit tests for imperal_sdk.rpc.codec — pure encode/decode functions.

Spec: superpowers/specs/2026-04-27-w2-pydantic-rpc-design.md §5.1, §8.2.
"""
import copy
import pytest
from pydantic import ValidationError

from imperal_sdk.rpc.contract import (
    ENVELOPE_VERSION,
    RpcStatus,
    RpcErrorCategory,
    RpcError,
    RpcRequest,
    RpcReply,
)
from imperal_sdk.rpc.codec import (
    DecodeResult,
    encode_request,
    encode_reply,
    decode_request,
    decode_reply,
    build_error_reply,
    should_cache_reply,
    is_legacy_envelope,
)


def _valid_request_kwargs() -> dict:
    return dict(
        corr_id="0123456789abcdef",
        user_id="imp_u_user_42",
        tenant_id="default",
        agency_id=None,
        email="user@example.com",
        role="user",
        scopes=["notes:read"],
        attributes={},
        app_id="notes",
        function="create_note",
        params={"title": "t", "body": "b"},
        reply_list="imperal:rpc:reply:0123456789abcdef",
        deadline_ns=1_700_000_000_000_000_000,
        submitted_at_ns=1_700_000_000_000_000_000,
    )


def test_encode_decode_request_round_trip():
    req = RpcRequest(**_valid_request_kwargs())
    payload = encode_request(req)
    assert payload["v"] == 1
    result = decode_request(payload)
    assert isinstance(result, DecodeResult)
    assert result.request == req
    assert result.reply is None
    assert result.legacy_envelope is False


def test_decode_request_loose_accepts_missing_v():
    payload = _valid_request_kwargs()  # no v field
    payload.pop("v", None)
    result = decode_request(payload, strict_version=False)
    assert result.request.v == 1
    assert result.legacy_envelope is True


def test_decode_request_strict_rejects_missing_v():
    payload = _valid_request_kwargs()
    payload.pop("v", None)
    with pytest.raises(ValidationError) as exc:
        decode_request(payload, strict_version=True)
    assert "v" in str(exc.value)


def test_decode_request_does_not_mutate_caller_payload():
    payload = _valid_request_kwargs()  # no v
    snapshot = copy.deepcopy(payload)
    decode_request(payload, strict_version=False)
    assert payload == snapshot, "codec must not mutate caller's dict"


def _valid_reply_kwargs() -> dict:
    return dict(
        corr_id="0123456789abcdef",
        status=RpcStatus.SUCCESS,
        result={"status": "ok", "data": {"id": "x"}},
        worker_id="whm-ai-worker-1",
        started_at_ns=1_700_000_000_000_000_000,
        finished_at_ns=1_700_000_000_042_000_000,
        error=None,
    )


def test_encode_decode_reply_round_trip_success():
    rep = RpcReply(**_valid_reply_kwargs())
    payload = encode_reply(rep)
    result = decode_reply(payload)
    assert result.reply == rep
    assert result.request is None
    assert result.legacy_envelope is False


def test_decode_reply_loose_accepts_missing_v():
    payload = _valid_reply_kwargs()
    payload.pop("v", None)
    result = decode_reply(payload, strict_version=False)
    assert result.reply.v == 1
    assert result.legacy_envelope is True


def test_decode_reply_strict_rejects_missing_v():
    payload = _valid_reply_kwargs()
    payload.pop("v", None)
    with pytest.raises(ValidationError):
        decode_reply(payload, strict_version=True)


def test_is_legacy_envelope():
    assert is_legacy_envelope({}) is True
    assert is_legacy_envelope({"a": 1}) is True
    assert is_legacy_envelope({"v": 1}) is False
    assert is_legacy_envelope({"v": 2, "x": "y"}) is False


def test_build_error_reply_default_finished_at():
    rep = build_error_reply(
        corr_id="0123456789abcdef",
        category=RpcErrorCategory.INFRASTRUCTURE,
        message="redis down",
        retryable=True,
        worker_id="w-1",
        started_at_ns=1_700_000_000_000_000_000,
    )
    assert rep.status == RpcStatus.ERROR
    assert rep.result is None
    assert rep.error.category == RpcErrorCategory.INFRASTRUCTURE
    assert rep.error.retryable is True
    assert rep.finished_at_ns >= rep.started_at_ns


def test_build_error_reply_trims_long_message():
    long_msg = "x" * 1024
    rep = build_error_reply(
        corr_id="0123456789abcdef",
        category=RpcErrorCategory.APPLICATION,
        message=long_msg,
        retryable=False,
        worker_id="w-1",
        started_at_ns=1,
        finished_at_ns=2,
    )
    assert len(rep.error.message) == 512


@pytest.mark.parametrize(
    "category,expected",
    [
        (RpcErrorCategory.APPLICATION, True),
        (RpcErrorCategory.TENANT_MISMATCH, True),
        (RpcErrorCategory.SCHEMA_VIOLATION, True),
        (RpcErrorCategory.INFRASTRUCTURE, False),
        (RpcErrorCategory.TIMEOUT, False),
    ],
)
def test_should_cache_reply_truth_table(category, expected):
    err_reply = build_error_reply(
        corr_id="0123456789abcdef",
        category=category,
        message="x",
        retryable=False,
        worker_id="w",
        started_at_ns=1,
        finished_at_ns=2,
    )
    assert should_cache_reply(err_reply) is expected


def test_should_cache_reply_success_always_true():
    rep = RpcReply(**_valid_reply_kwargs())
    assert should_cache_reply(rep) is True


def test_decode_request_malformed_raises_validation_error():
    bad = {"v": 1, "corr_id": "short"}  # missing required fields + bad corr_id
    with pytest.raises(ValidationError):
        decode_request(bad)


def test_decode_v2_currently_rejected_until_evolution_lands():
    payload = _valid_request_kwargs() | {"v": 2}
    with pytest.raises(ValidationError):
        decode_request(payload)
