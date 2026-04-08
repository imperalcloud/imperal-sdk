# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import httpx


class NotifyClient:
    def __init__(self, gateway_url: str, auth_token: str = "", user_id: str = "", service_token: str = ""):
        self._gateway_url = gateway_url.rstrip("/")
        self._auth_token = auth_token or service_token
        self._user_id = user_id

    async def __call__(self, message: str, **kwargs) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(f"{self._gateway_url}/v1/internal/notify", json={"user_id": self._user_id, "message": message, **kwargs}, headers={"Authorization": f"Bearer {self._auth_token}"}, timeout=10)
