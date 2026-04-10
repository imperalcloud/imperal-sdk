# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx

from imperal_sdk.types.pagination import Page


@dataclass
class Document:
    id: str
    collection: str
    data: dict
    created_at: str | None = None
    updated_at: str | None = None

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)


class StoreClient:
    """Tier 1: Managed document storage via Auth Gateway internal API."""

    def __init__(self, gateway_url: str, auth_token: str = "", extension_id: str = "", user_id: str = "", tenant_id: str = "default", service_token: str = ""):
        self._gateway_url = gateway_url.rstrip("/")
        self._auth_token = auth_token or service_token
        self._extension_id = extension_id
        self._user_id = user_id
        self._tenant_id = tenant_id

    def _headers(self) -> dict:
        return {"X-Service-Token": self._auth_token, "X-Extension-ID": self._extension_id, "X-Tenant-ID": self._tenant_id}

    async def create(self, collection: str, data: dict) -> Document:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._gateway_url}/v1/internal/store", json={"collection": collection, "data": data, "user_id": self._user_id, "extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            r = resp.json()
            return Document(id=r["id"], collection=collection, data=r.get("data", data), created_at=r.get("created_at"), updated_at=r.get("updated_at"))

    async def get(self, collection: str, doc_id: str) -> Document | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._gateway_url}/v1/internal/store/{collection}/{doc_id}", params={"extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=30)
            if resp.status_code == 404: return None
            resp.raise_for_status()
            r = resp.json()
            return Document(id=r["id"], collection=collection, data=r.get("data", {}), created_at=r.get("created_at"), updated_at=r.get("updated_at"))

    async def query(self, collection: str, where: dict | None = None, order_by: str | None = None, limit: int = 100) -> Page[Document]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._gateway_url}/v1/internal/store/{collection}/query", json={"where": where or {}, "order_by": order_by, "limit": limit, "extension_id": self._extension_id, "user_id": self._user_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            raw = resp.json()
            # Support both list response and paginated envelope {"data": [...], "cursor": ..., "has_more": ...}
            if isinstance(raw, list):
                items = [Document(id=r["id"], collection=collection, data=r.get("data", {}), created_at=r.get("created_at"), updated_at=r.get("updated_at")) for r in raw]
                return Page(data=items, has_more=False)
            items = [Document(id=r["id"], collection=collection, data=r.get("data", {}), created_at=r.get("created_at"), updated_at=r.get("updated_at")) for r in raw.get("data", [])]
            return Page(data=items, cursor=raw.get("cursor"), has_more=raw.get("has_more", False), total=raw.get("total"))

    async def update(self, collection: str, doc_id: str, data: dict) -> Document:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{self._gateway_url}/v1/internal/store/{collection}/{doc_id}", json={"data": data, "extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            r = resp.json()
            return Document(id=r["id"], collection=collection, data=r.get("data", data), created_at=r.get("created_at"), updated_at=r.get("updated_at"))

    async def delete(self, collection: str, doc_id: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{self._gateway_url}/v1/internal/store/{collection}/{doc_id}", params={"extension_id": self._extension_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=30)
            return resp.status_code == 200

    async def count(self, collection: str, where: dict | None = None) -> int:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._gateway_url}/v1/internal/store/{collection}/count", json={"where": where or {}, "extension_id": self._extension_id, "user_id": self._user_id, "tenant_id": self._tenant_id}, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            return resp.json().get("count", 0)
