# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from typing import Any
import httpx


class SkeletonClient:
    def __init__(self, gateway_url: str, auth_token: str = "", extension_id: str = "", user_id: str = "", service_token: str = ""):
        self._gateway_url = gateway_url.rstrip("/")
        self._token = auth_token or service_token
        self._extension_id = extension_id
        self._user_id = user_id

    def _headers(self) -> dict:
        return {"X-Service-Token": self._token}

    async def get(self, section: str) -> Any:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._gateway_url}/v1/internal/skeleton/{self._user_id}/{section}",
                params={"extension_id": self._extension_id},
                headers=self._headers(), timeout=10
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json().get("data")

    async def update(self, section: str, data: Any) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self._gateway_url}/v1/internal/skeleton/{self._user_id}/{section}",
                json={"data": data, "extension_id": self._extension_id},
                headers=self._headers(), timeout=10
            )
            resp.raise_for_status()
