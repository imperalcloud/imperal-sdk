# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import httpx


class StorageClient:
    def __init__(self, gateway_url: str, auth_token: str, extension_id: str, tenant_id: str):
        self._gateway_url = gateway_url.rstrip("/")
        self._auth_token = auth_token
        self._extension_id = extension_id
        self._tenant_id = tenant_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth_token}"}

    async def upload(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._gateway_url}/v1/internal/storage/upload", files={"file": (path, data, content_type)}, data={"path": path, "extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            return resp.json().get("url", "")

    async def download(self, path: str) -> bytes:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._gateway_url}/v1/internal/storage/download", params={"path": path, "extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=60)
            resp.raise_for_status()
            return resp.content

    async def delete(self, path: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self._gateway_url}/v1/internal/storage", params={"path": path, "extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=10)
            return resp.status_code == 200

    async def list(self, prefix: str = "") -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._gateway_url}/v1/internal/storage/list", params={"prefix": prefix, "extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json().get("files", [])
