"""Permanent regression guard: RpcReply/RpcError boundary must never carry engine tokens.

Three assertions (structural, behavioral, negative-control) constitute the seal contract.
"""
import json
import typing

import pytest

from imperal_sdk.rpc import RpcReply, RpcError, RpcStatus
from imperal_sdk.rpc.contract import RpcErrorCategory
from imperal_sdk.rpc.codec import encode_reply

# Mirrors the gateway's error_normalize.py FORBIDDEN_ENGINE_TOKENS (cross-repo).
FORBIDDEN = (
    "temporal",
    "directcallworkflow",
    "task_queue",
    "run_id",
    "workflow_id",
    "workflowfailureerror",
)


def _assert_engine_free(blob: str) -> None:
    low = blob.lower()
    hits = [t for t in FORBIDDEN if t in low]
    if hits:
        raise AssertionError(
            f"engine token(s) {hits} leaked into RPC boundary: {blob!r}"
        )


def test_rpc_models_fields_are_primitive_dtos():
    """Structural lock: no RPC model field may be a non-primitive (engine) type."""
    # RpcErrorCategory is a legitimate bounded DTO enum (not an engine type).
    # Literal[1] (the v-discriminator) resolves to int — also legitimate.
    allowed = {str, int, float, bool, dict, list, type(None), RpcError, RpcStatus, RpcErrorCategory}
    for model in (RpcReply, RpcError):
        for name, field in model.model_fields.items():
            ann = field.annotation
            origin = typing.get_origin(ann)
            # Literal[x, ...] — each arg is a value, not a type; resolve to its type.
            if origin is typing.Literal:
                bases: set = {type(v) for v in typing.get_args(ann)}
            else:
                args = typing.get_args(ann)
                bases = set(args) if args else {ann}
            for b in bases:
                resolved = typing.get_origin(b) or b
                assert resolved in allowed or b in allowed, (
                    f"{model.__name__}.{name} has non-primitive type {b!r}"
                )


def test_error_reply_serializes_engine_free():
    """A reply built from a representative engine-failure carries only the opaque code."""
    reply = RpcReply(
        corr_id="c" * 16,
        status=RpcStatus.ERROR,
        result=None,
        worker_id="w1",
        started_at_ns=1,
        finished_at_ns=2,
        error=RpcError(
            category=RpcErrorCategory.INFRASTRUCTURE,
            message="execution_failed",
            retryable=False,
        ),
    )
    _assert_engine_free(json.dumps(encode_reply(reply)))


def test_a_leaky_error_message_would_be_caught():
    """Negative control: the guard actually fires on an engine token."""
    leaky = RpcReply(
        corr_id="c" * 16,
        status=RpcStatus.ERROR,
        result=None,
        worker_id="w1",
        started_at_ns=1,
        finished_at_ns=2,
        error=RpcError(
            category=RpcErrorCategory.INFRASTRUCTURE,
            message="WorkflowFailureError run_id=deadbeef task_queue=platform",
            retryable=False,
        ),
    )
    with pytest.raises(AssertionError):
        _assert_engine_free(json.dumps(encode_reply(leaky)))
