# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import httpx

from imperal_sdk.types.models import HTTPResponse


def _wrap(resp: httpx.Response) -> HTTPResponse:
    """Convert httpx.Response to typed HTTPResponse."""
    content_type = resp.headers.get("content-type", "")
    if "json" in content_type:
        try:
            body = resp.json()
        except Exception:
            body = resp.text
    elif resp.content:
        # Return text for text/* or small responses; bytes otherwise
        try:
            body = resp.text
        except Exception:
            body = resp.content
    else:
        body = ""
    return HTTPResponse(status_code=resp.status_code, body=body, headers=dict(resp.headers))


class HTTPClient:
    def __init__(self, timeout: int = 30, max_redirects: int = 5):
        self._timeout = timeout
        self._max_redirects = max_redirects

    async def get(self, url: str, **kwargs) -> HTTPResponse:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return _wrap(await client.get(url, **kwargs))

    async def post(self, url: str, **kwargs) -> HTTPResponse:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return _wrap(await client.post(url, **kwargs))

    async def put(self, url: str, **kwargs) -> HTTPResponse:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return _wrap(await client.put(url, **kwargs))

    async def patch(self, url: str, **kwargs) -> HTTPResponse:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return _wrap(await client.patch(url, **kwargs))

    async def delete(self, url: str, **kwargs) -> HTTPResponse:
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, max_redirects=self._max_redirects) as client:
            return _wrap(await client.delete(url, **kwargs))
