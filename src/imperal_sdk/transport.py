# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Isolated Transport Contract for Imperal SDK Gateway Communication.

Decouples high-level SDK namespaces (billing, store, rbac, secrets, notify)
from direct network runtime quirks, asyncio loop nuances, and internal cluster ports.
Supports:
- HttpTransport: Standard keep-alive connection pool with automatic loop resilience.
- OfflineTransport: Zero-network in-memory transport for deterministic testing.
"""
from __future__ import annotations

import abc
from typing import Any, Dict, Optional, Protocol, runtime_checkable
import httpx

from imperal_sdk._http_retry import retry_transient
from imperal_sdk._shared_http import shared_http
from imperal_sdk.errors import APIError, AuthError, NotFoundError


@runtime_checkable
class GatewayTransport(Protocol):
    """Protocol defining isolated gateway transport contract."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        timeout: float = 15.0,
        op: str = "",
    ) -> Any:
        """Execute one gateway request and return parsed response JSON."""
        ...


class DefaultHttpTransport:
    """Production HTTP transport with retry policy and loop resilience."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        timeout: float = 15.0,
        op: str = "",
    ) -> Any:
        op_name = op or f"{method} {url}"

        async def _once():
            async with shared_http(timeout=timeout) as client:
                return await client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=headers,
                )

        resp = await retry_transient(_once, op=op_name)

        if resp.status_code == 404:
            raise NotFoundError(f"Resource not found: {op_name}")
        if resp.status_code in (401, 403):
            raise AuthError(f"Authentication failed: {resp.status_code} {resp.text}")
        if resp.status_code >= 400:
            raise APIError(f"API request failed: {resp.status_code} {resp.text}", resp.status_code)

        if resp.content:
            return resp.json()
        return {}


class OfflineTransport:
    """Zero-network deterministic mock transport for local testing."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None) -> None:
        self.responses: Dict[str, Any] = responses or {}
        self.recorded_requests: list[Dict[str, Any]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        timeout: float = 15.0,
        op: str = "",
    ) -> Any:
        self.recorded_requests.append({
            "method": method,
            "url": url,
            "headers": headers,
            "params": params,
            "json": json_data,
        })
        for pattern, res in self.responses.items():
            if pattern in url:
                if callable(res):
                    return res(method, url, json_data)
                return res
        return {}
