# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Test GatewayTransport and transport isolation contract."""
import pytest
from imperal_sdk._gateway import GatewayClient
from imperal_sdk.transport import OfflineTransport


@pytest.mark.asyncio
async def test_gateway_client_uses_isolated_transport():
    transport = OfflineTransport(
        responses={
            "/v1/billing/balance": {"balance": 75000, "currency": "credits"},
        }
    )

    client = GatewayClient(
        gateway_url="https://gateway.imperal.local",
        service_token="test_srv_token",
        user_id="imp_u_test",
        extension_id="test_ext",
        tenant_id="default",
    )

    result = await client._call("GET", "/v1/billing/balance", transport=transport)
    assert result == {"balance": 75000, "currency": "credits"}
    assert len(transport.recorded_requests) == 1
    req = transport.recorded_requests[0]
    assert req["method"] == "GET"
    assert req["url"] == "https://gateway.imperal.local/v1/billing/balance"
    assert req["headers"]["X-Service-Token"] == "test_srv_token"
    assert req["headers"]["X-Acting-User"] == "imp_u_test"
    assert req["headers"]["X-Extension-ID"] == "test_ext"
