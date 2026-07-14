# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""POST /v1/internal/notify wire payload — extension_id attribution
(Notification Preferences v1, spec section 5). Mirrors the respx style of
``test_sdk_matches_kernel_contract.py`` (asyncio_mode=auto — plain
``async def`` needs no marker)."""
import json

import httpx
import respx

from imperal_sdk.notify.client import NotifyClient


@respx.mock
async def test_call_includes_extension_id():
    respx.post("http://gw/v1/internal/notify").mock(
        return_value=httpx.Response(200, json={"status": "queued"}))
    c = NotifyClient(gateway_url="http://gw", service_token="t", user_id="u1",
                      extension_id="sharelock-v2")
    await c("hello", priority="high")

    payload = json.loads(respx.calls.last.request.read())
    assert payload["user_id"] == "u1" and payload["message"] == "hello"
    assert payload["extension_id"] == "sharelock-v2"
    assert payload["priority"] == "high"


@respx.mock
async def test_empty_extension_id_omitted():
    respx.post("http://gw/v1/internal/notify").mock(
        return_value=httpx.Response(200, json={"status": "queued"}))
    c = NotifyClient(gateway_url="http://gw", service_token="t", user_id="u1")
    await c("hello")

    payload = json.loads(respx.calls.last.request.read())
    assert "extension_id" not in payload


@respx.mock
async def test_explicit_kwarg_wins_over_constructor_extension_id():
    respx.post("http://gw/v1/internal/notify").mock(
        return_value=httpx.Response(200, json={"status": "queued"}))
    c = NotifyClient(gateway_url="http://gw", service_token="t", user_id="u1",
                      extension_id="sharelock-v2")
    await c("hello", extension_id="override-ext")

    payload = json.loads(respx.calls.last.request.read())
    assert payload["extension_id"] == "override-ext"
