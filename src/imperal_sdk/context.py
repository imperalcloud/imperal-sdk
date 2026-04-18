# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from imperal_sdk.auth.user import User, Tenant

if TYPE_CHECKING:
    from imperal_sdk.types.models import (
        Document, CompletionResult, LimitsResult, SubscriptionInfo,
        BalanceInfo, FileInfo, HTTPResponse,
    )
    from imperal_sdk.types.pagination import Page


@runtime_checkable
class StoreProtocol(Protocol):
    async def create(self, collection: str, data: dict) -> Document: ...
    async def get(self, collection: str, doc_id: str) -> Document | None: ...
    async def query(self, collection: str, where: dict | None = None, order_by: str | None = None, limit: int = 100, cursor: str | None = None) -> Page[Document]: ...
    async def update(self, collection: str, doc_id: str, data: dict) -> Document: ...
    async def delete(self, collection: str, doc_id: str) -> bool: ...
    async def count(self, collection: str, where: dict | None = None) -> int: ...


@runtime_checkable
class DBProtocol(Protocol):
    async def acquire(self): ...
    async def session(self): ...


@runtime_checkable
class AIProtocol(Protocol):
    async def complete(self, prompt: str, model: str = "", **kwargs) -> CompletionResult: ...


@runtime_checkable
class SkeletonProtocol(Protocol):
    async def get(self, section: str) -> Any: ...
    async def update(self, section: str, data: Any) -> None: ...


@runtime_checkable
class BillingProtocol(Protocol):
    async def check_limits(self) -> LimitsResult: ...
    async def get_subscription(self) -> SubscriptionInfo: ...
    async def track_usage(self, tokens: int, resource: str = "llm") -> None: ...
    async def get_balance(self) -> BalanceInfo: ...


@runtime_checkable
class NotifyProtocol(Protocol):
    # Preferred invocation: ``await ctx.notify("message", priority="high")``.
    # Matches the concrete NotifyClient.__call__ signature. Every production
    # extension uses this style.
    async def __call__(self, message: str, **kwargs) -> None: ...
    # Alias kept for historical test doc compatibility; NotifyClient forwards
    # this to __call__. Prefer __call__ in new code.
    async def send(self, message: str, channel: str = "in_app", **kwargs) -> None: ...


@runtime_checkable
class StorageProtocol(Protocol):
    async def upload(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> FileInfo: ...
    async def download(self, path: str) -> bytes: ...
    async def delete(self, path: str) -> bool: ...
    async def list(self, prefix: str = "") -> Page[FileInfo]: ...


@runtime_checkable
class HTTPProtocol(Protocol):
    async def get(self, url: str, **kwargs) -> HTTPResponse: ...
    async def post(self, url: str, **kwargs) -> HTTPResponse: ...
    async def put(self, url: str, **kwargs) -> HTTPResponse: ...
    async def patch(self, url: str, **kwargs) -> HTTPResponse: ...
    async def delete(self, url: str, **kwargs) -> HTTPResponse: ...


@runtime_checkable
class ToolsProtocol(Protocol):
    async def discover(self, query: str, top_k: int = 3) -> list: ...
    async def call(self, activity_name: str, params: dict) -> Any: ...


@runtime_checkable
class ConfigProtocol(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...
    def get_section(self, section: str) -> dict: ...
    def require(self, key: str) -> Any: ...
    def all(self) -> dict: ...


@runtime_checkable
class ExtensionsProtocol(Protocol):
    async def call(self, app_id: str, method: str, **kwargs) -> Any: ...
    async def emit(self, event_type: str, data: dict) -> None: ...


@dataclass
class TimeContext:
    """Kernel-injected time context. Read-only, no network call."""
    timezone: str = "UTC"
    utc_offset: str = "+00:00"
    now_utc: str = ""
    now_local: str = ""
    hour_local: int = 0
    is_business_hours: bool = False


@dataclass
class Context:
    """The context object passed to every extension tool/signal/schedule call."""
    user: User
    tenant: Tenant | None = None
    store: StoreProtocol | None = None
    db: DBProtocol | None = None
    ai: AIProtocol | None = None
    skeleton: SkeletonProtocol | None = None
    billing: BillingProtocol | None = None
    notify: NotifyProtocol | None = None
    storage: StorageProtocol | None = None
    http: HTTPProtocol | None = None
    tools: ToolsProtocol | None = None
    config: ConfigProtocol | None = None
    extensions: ExtensionsProtocol | None = None
    time: TimeContext = field(default_factory=TimeContext)
    _extension_id: str = ""
    _metadata: dict = field(default_factory=dict)

    async def progress(self, percent: float, message: str = "") -> None:
        """Report task progress. May raise TaskCancelled if user cancelled."""
        cb = getattr(self, "_progress_callback", None)
        if cb:
            await cb(percent, message)

    async def log(self, message: str, level: str = "info") -> None:
        """Structured log visible in extension dashboard."""
        import logging
        logger = logging.getLogger(f"ext.{self._extension_id}")
        getattr(logger, level, logger.info)(message)
