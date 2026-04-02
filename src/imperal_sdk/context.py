# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StoreProtocol(Protocol):
    async def create(self, collection: str, data: dict) -> Any: ...
    async def get(self, collection: str, doc_id: str) -> Any: ...
    async def query(self, collection: str, where: dict | None = None, order_by: str | None = None, limit: int = 100) -> list: ...
    async def update(self, collection: str, doc_id: str, data: dict) -> Any: ...
    async def delete(self, collection: str, doc_id: str) -> bool: ...
    async def count(self, collection: str, where: dict | None = None) -> int: ...


@runtime_checkable
class DBProtocol(Protocol):
    async def acquire(self): ...
    async def session(self): ...


@runtime_checkable
class AIProtocol(Protocol):
    async def complete(self, prompt: str, model: str = "claude-sonnet", **kwargs) -> Any: ...


@runtime_checkable
class SkeletonProtocol(Protocol):
    async def get(self, section: str) -> Any: ...
    async def update(self, section: str, data: Any) -> None: ...


@runtime_checkable
class BillingProtocol(Protocol):
    async def check_limits(self, user: Any = None) -> Any: ...
    async def get_subscription(self, user: Any = None) -> Any: ...


@runtime_checkable
class NotifyProtocol(Protocol):
    async def __call__(self, message: str, **kwargs) -> None: ...


@runtime_checkable
class StorageProtocol(Protocol):
    async def upload(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    async def download(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> bool: ...
    async def list(self, prefix: str = "") -> list[str]: ...


@runtime_checkable
class HTTPProtocol(Protocol):
    async def get(self, url: str, **kwargs) -> Any: ...
    async def post(self, url: str, **kwargs) -> Any: ...


@dataclass
class Context:
    """The context object passed to every extension tool/signal/schedule call."""
    user: Any
    tenant: Any = None
    store: StoreProtocol | None = None
    db: DBProtocol | None = None
    ai: AIProtocol | None = None
    skeleton: SkeletonProtocol | None = None
    billing: BillingProtocol | None = None
    notify: NotifyProtocol | None = None
    storage: StorageProtocol | None = None
    http: HTTPProtocol | None = None
    _extension_id: str = ""
    _metadata: dict = field(default_factory=dict)
