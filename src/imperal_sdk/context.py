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
    # Agency tenancy + white-label theming (2026-04-19). agency_id is the
    # data-isolation boundary; agency_theme is the raw dict form of the
    # AgencyTheme payload populated by the kernel on workflow start. Parse
    # via ``imperal_sdk.ui.theme(ctx)`` for a typed accessor.
    agency_id: str | None = None
    agency_theme: dict | None = None
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

    def as_user(self, user_id: str) -> "Context":
        """Return scoped Context for target user_id.

        System-context only. Rewires per-user clients (store, skeleton,
        notify, billing) with new user_id; inherits ai/storage/http/config.

        Invariants: I-AS-USER-1 (system-context guard),
                    I-AS-USER-2 (only user.id changes; extension/tenant/agency preserved).

        Raises:
            RuntimeError: caller is not system-context.
            ValueError: user_id is empty or "__system__".
        """
        if self.user.id != "__system__":
            raise RuntimeError(
                f"ctx.as_user() requires system context (got {self.user.id!r})"
            )
        if not user_id or user_id == "__system__":
            raise ValueError(
                f"target user_id must be non-empty, non-system: {user_id!r}"
            )

        new_user = User(
            id=user_id,
            email=self.user.email,
            tenant_id=self.user.tenant_id,
            agency_id=getattr(self.user, "agency_id", None),
            role=self.user.role,
            scopes=list(self.user.scopes),
            attributes=dict(self.user.attributes, scoped_from="__system__"),
        )

        new_store = self._rebuild_store_for(user_id) if self.store else None
        new_skeleton = self._rebuild_skeleton_for(user_id) if self.skeleton else None
        new_notify = self._rebuild_notify_for(user_id) if self.notify else None
        new_billing = self._rebuild_billing_for(user_id) if self.billing else None

        return Context(
            user=new_user,
            tenant=self.tenant,
            store=new_store,
            skeleton=new_skeleton,
            notify=new_notify,
            billing=new_billing,
            # Reused — not user-scoped
            ai=self.ai,
            db=self.db,
            storage=self.storage,
            http=self.http,
            tools=self.tools,
            config=self.config,
            extensions=self.extensions,
            time=self.time,
            agency_id=self.agency_id,
            agency_theme=self.agency_theme,
            _extension_id=self._extension_id,
            _metadata=dict(self._metadata),
        )

    def _rebuild_store_for(self, user_id: str):
        from imperal_sdk.store.client import StoreClient
        return StoreClient(
            gateway_url=self.store._gateway_url,
            service_token=self.store._auth_token,
            extension_id=self._extension_id,
            user_id=user_id,
            tenant_id=self.user.tenant_id,
        )

    def _rebuild_skeleton_for(self, user_id: str):
        from imperal_sdk.skeleton.client import SkeletonClient
        # SkeletonClient stores its token as `_token` (accepts both
        # auth_token= and service_token= in __init__, unified at construction).
        return SkeletonClient(
            gateway_url=self.skeleton._gateway_url,
            service_token=self.skeleton._token,
            extension_id=self._extension_id,
            user_id=user_id,
        )

    def _rebuild_notify_for(self, user_id: str):
        from imperal_sdk.notify.client import NotifyClient
        return NotifyClient(
            gateway_url=self.notify._gateway_url,
            service_token=self.notify._auth_token,
            user_id=user_id,
        )

    def _rebuild_billing_for(self, user_id: str):
        try:
            from imperal_sdk.billing.client import BillingClient
        except ImportError:
            return None
        # BillingClient separates service_token and auth_token; preserve both.
        return BillingClient(
            gateway_url=self.billing._gateway_url,
            service_token=getattr(self.billing, "_service_token", ""),
            auth_token=getattr(self.billing, "_auth_token", ""),
            user_id=user_id,
        )
