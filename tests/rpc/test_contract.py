"""Unit tests for imperal_sdk.rpc.contract — Pydantic envelope models.

Spec: superpowers/specs/2026-04-27-w2-pydantic-rpc-design.md §5.1, §8.1.
"""
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


def test_envelope_version_is_literal_one():
    assert ENVELOPE_VERSION == 1


def test_rpc_status_members():
    assert RpcStatus.SUCCESS.value == "success"
    assert RpcStatus.ERROR.value == "error"


def test_rpc_error_category_has_five_members():
    expected = {"application", "infrastructure", "timeout", "schema_violation", "tenant_mismatch"}
    actual = {m.value for m in RpcErrorCategory}
    assert actual == expected


def _valid_request_kwargs() -> dict:
    return dict(
        corr_id="0123456789abcdef" * 1,           # 16 chars min
        user_id="imp_u_test_user_42",
        tenant_id="default",
        agency_id=None,
        email="user@example.com",
        role="user",
        scopes=["notes:read"],
        attributes={"source": "test"},
        app_id="notes",
        function="create_note",
        params={"title": "x", "body": "y"},
        reply_list="imperal:rpc:reply:0123456789abcdef",
        deadline_ns=1_700_000_000_000_000_000,
        submitted_at_ns=1_700_000_000_000_000_000,
    )


def test_rpc_request_round_trip():
    req = RpcRequest(**_valid_request_kwargs())
    dumped = req.model_dump_json()
    reloaded = RpcRequest.model_validate_json(dumped)
    assert reloaded == req
    assert reloaded.v == 1


def test_rpc_request_extra_ignore_drops_unknown_field():
    payload = _valid_request_kwargs() | {"v": 1, "future_field": "ignored"}
    req = RpcRequest.model_validate(payload)
    assert not hasattr(req, "future_field")


def test_rpc_request_frozen_blocks_mutation():
    req = RpcRequest(**_valid_request_kwargs())
    with pytest.raises(ValidationError):
        req.corr_id = "tampered"  # type: ignore[misc]


def test_rpc_request_corr_id_length_constraint():
    bad = _valid_request_kwargs() | {"corr_id": "short"}
    with pytest.raises(ValidationError) as exc:
        RpcRequest(**bad)
    assert "corr_id" in str(exc.value)


def test_rpc_request_user_id_must_be_non_empty():
    bad = _valid_request_kwargs() | {"user_id": ""}
    with pytest.raises(ValidationError):
        RpcRequest(**bad)


def test_rpc_request_v_must_be_one():
    bad = _valid_request_kwargs() | {"v": 2}
    with pytest.raises(ValidationError):
        RpcRequest(**bad)


def _valid_reply_kwargs() -> dict:
    return dict(
        corr_id="0123456789abcdef",
        status=RpcStatus.SUCCESS,
        result={"status": "ok", "data": {"id": "n-42"}},
        worker_id="whm-ai-worker-2",
        started_at_ns=1_700_000_000_000_000_000,
        finished_at_ns=1_700_000_000_042_000_000,
        error=None,
    )


def test_rpc_reply_round_trip_success():
    rep = RpcReply(**_valid_reply_kwargs())
    reloaded = RpcReply.model_validate_json(rep.model_dump_json())
    assert reloaded == rep
    assert reloaded.error is None


def test_rpc_reply_round_trip_error():
    err = RpcError(category=RpcErrorCategory.APPLICATION, message="boom", retryable=False)
    rep = RpcReply(**(_valid_reply_kwargs() | {"status": RpcStatus.ERROR, "result": None, "error": err}))
    reloaded = RpcReply.model_validate_json(rep.model_dump_json())
    assert reloaded == rep
    assert reloaded.error.category == RpcErrorCategory.APPLICATION


def test_rpc_error_frozen():
    err = RpcError(category=RpcErrorCategory.TIMEOUT, message="t", retryable=True)
    with pytest.raises(ValidationError):
        err.message = "tampered"  # type: ignore[misc]


def test_discriminator_evolution_path_works():
    """A v2 envelope class can co-exist via discriminated union.

    This is the proof that the v: Literal[1] choice keeps the wire
    forward-compatible — when we ship v2, we add another model class
    and tag-union them.
    """
    from typing import Annotated, Literal as L, Union as U
    from pydantic import Field as PField, TypeAdapter
    from pydantic import BaseModel
    from typing import Any

    class _RpcReqV2(BaseModel):
        v: L[2]
        payload: dict[str, Any]

    Adapter = TypeAdapter(
        Annotated[U[RpcRequest, _RpcReqV2], PField(discriminator="v")]
    )

    v1 = _valid_request_kwargs() | {"v": 1}
    parsed_v1 = Adapter.validate_python(v1)
    assert isinstance(parsed_v1, RpcRequest)

    v2 = {"v": 2, "payload": {"x": 1}}
    parsed_v2 = Adapter.validate_python(v2)
    assert isinstance(parsed_v2, _RpcReqV2)
