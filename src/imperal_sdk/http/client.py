# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import httpx


class HTTPClient:
    def __init__(self, timeout: int = 30, max_redirects: int = 5):
        self._timeout = timeout
        self._max_redirects = max_redirects

    async def get(self, url: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return await client.get(url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return await client.post(url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return await client.put(url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return await client.patch(url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return await client.delete(url, **kwargs)
