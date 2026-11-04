# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""L1 SDK tests for ctx.store.list_users — fake HTTP via respx."""
from __future__ import annotations

import pytest
import httpx

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


async def _run_list(client, **kwargs):
    return [uid async for uid in client.list_users(**kwargs)]


async def test_raises_if_user_context():
    """I-LIST-USERS-1 — SDK guard rejects non-system actor."""
    client = _make_client(user_id="real-user-id")
    with pytest.raises(RuntimeError, match="system context"):
        await _run_list(client, collection="c")


async def test_yields_single_page(respx_mock):
    respx_mock.get("http://test-gw/v1/internal/store/c/list_users").mock(
        return_value=httpx.Response(200, json={
            "user_ids": ["u1", "u2"], "next_cursor": None, "truncated": False,
        }))
    client = _make_client()
    assert await _run_list(client, collection="c") == ["u1", "u2"]


async def test_paginates_until_exhausted(respx_mock):
    respx_mock.get("http://test-gw/v1/internal/store/c/list_users").mock(
        side_effect=[
            httpx.Response(200, json={
                "user_ids": ["u1", "u2"], "next_cursor": "2", "truncated": False}),
            httpx.Response(200, json={
                "user_ids": ["u3"], "next_cursor": None, "truncated": False}),
        ])
    client = _make_client()
    assert await _run_list(client, collection="c") == ["u1", "u2", "u3"]


async def test_raises_store_unavailable_on_503(respx_mock):
    respx_mock.get("http://test-gw/v1/internal/store/c/list_users").mock(
        return_value=httpx.Response(503))
    client = _make_client()
    with pytest.raises(StoreUnavailable):
        await _run_list(client, collection="c")


async def test_forbidden_collection_chars():
    client = _make_client()
    for bad in ["a:b", "a*b", "a?b", "a[b", "a/b", "a b"]:
        with pytest.raises(ValueError):
            await _run_list(client, collection=bad)


async def test_page_size_bounds():
    client = _make_client()
    with pytest.raises(ValueError):
        await _run_list(client, collection="c", page_size=0)
    with pytest.raises(ValueError):
        await _run_list(client, collection="c", page_size=10001)
