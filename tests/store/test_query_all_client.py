# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""L1 SDK tests for ctx.store.query_all."""
from __future__ import annotations

import httpx
import pytest

from imperal_sdk.store.client import StoreClient
from imperal_sdk.store.exceptions import StoreUnavailable


def _make_client(user_id: str = "__system__") -> StoreClient:
    return StoreClient(
        gateway_url="http://test-gw",
        service_token="test-token",
        extension_id="test-ext",
        user_id=user_id,
        tenant_id="default",
    )


async def test_raises_if_user_context():
    client = _make_client(user_id="real-user")
    with pytest.raises(RuntimeError, match="system context"):
        await client.query_all(collection="c")


async def test_returns_docs(respx_mock):
    respx_mock.get("http://test-gw/v1/internal/store/c/all").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "d1",
                    "user_id": "u1",
                    "collection": "c",
                    "data": {"k": 1},
                    "created_at": "2026-04-22",
                    "updated_at": "2026-04-22",
                },
                {
                    "id": "d2",
                    "user_id": "u2",
                    "collection": "c",
                    "data": {"k": 2},
                    "created_at": "2026-04-22",
                    "updated_at": "2026-04-22",
                },
            ],
        )
    )
    client = _make_client()
    docs = await client.query_all(collection="c")
    assert len(docs) == 2
    assert docs[0].id == "d1"
    assert docs[0].user_id == "u1"
    assert docs[0].data == {"k": 1}
    assert docs[1].user_id == "u2"


async def test_raises_store_unavailable_on_503(respx_mock):
    respx_mock.get("http://test-gw/v1/internal/store/c/all").mock(
        return_value=httpx.Response(503)
    )
    client = _make_client()
    with pytest.raises(StoreUnavailable):
        await client.query_all(collection="c")


async def test_forbidden_chars_rejected():
    client = _make_client()
    with pytest.raises(ValueError):
        await client.query_all(collection="a:b")
