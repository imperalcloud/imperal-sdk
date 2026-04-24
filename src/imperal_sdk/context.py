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
    """Read-only skeleton accessor.

    v1.6.0 breaking change: ``update()`` removed. The kernel
    ``skeleton_save_section`` activity is the sole writer. Extensions
    return fresh data from their ``@ext.skeleton`` tool.

    Invariants: I-SKELETON-PROTOCOL-READ-ONLY, I-NO-SKELETON-PUT.
    """
    async def get(self, section: str) -> Any: ...


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


class _SkeletonAccessGuard:
    """Wraps a :class:`SkeletonProtocol` implementation; rejects access outside
    ``@ext.skeleton`` contexts.

    v1.6.0: ``ctx.skeleton`` is the LLM-facts snapshot consumed by the intent
    classifier. Only ``@ext.skeleton`` refresh tools are allowed to read it.
    Panels, regular tools, and chat functions must use ``ctx.cache`` for
    short-lived runtime data or ``ctx.store`` for persistent per-user state.

    Note the absence of an ``update`` method — consistent with
    :class:`SkeletonProtocol` v1.6.0 read-only contract; prevents a bypass
    path being re-introduced.

    Invariant: I-SKELETON-LLM-ONLY.
    """

    __slots__ = ("_client", "_tool_type")

    def __init__(self, client: Any, tool_type: str):
        self._client = client
        self._tool_type = tool_type

    async def get(self, section: str) -> Any:
        if self._tool_type != "skeleton":
            # Local import to avoid a cycle; errors depends on nothing,
            # but keep the indirection minimal for clarity.
            from imperal_sdk.errors import SkeletonAccessForbidden
            raise SkeletonAccessForbidden(
                f"ctx.skeleton.get() called from {self._tool_type!r} context; "
                "only @ext.skeleton tools may access skeleton."
            )
        return await self._client.get(section)


@dataclass
class Context:
    """The context object passed to every extension tool/signal/schedule call."""
    user: User
    tenant: Tenant | None = None
    store: StoreProtocol | None = None
    db: DBProtocol | None = None
    ai: AIProtocol | None = None
    # ``skeleton`` is a raw :class:`SkeletonProtocol` implementation supplied
    # by the kernel. In v1.6.0 it is wrapped by :class:`_SkeletonAccessGuard`
    # when surfaced via the :pyattr:`skeleton` property — direct access to
    # this field is deprecated and reserved for internal construction.
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
    # v1.6.0 skeleton + cache HMAC plumbing. ``_tool_type`` discriminates the
    # dispatch surface (``"skeleton"`` / ``"panel"`` / ``"tool"`` /
    # ``"chat_fn"``); ``_call_token`` is the per-invocation HMAC call-token
    # minted by the kernel and verified by the Auth GW on skeleton/cache
    # endpoints. Invariant: I-SKELETON-LLM-ONLY.
    _tool_type: str = "tool"
    _call_token: str = ""
    # Extension instance (for ctx.cache -> cache_model reverse lookup).
    # Populated by the kernel when constructing the Context; ``None`` in
    # minimal mock contexts. Wired in Task 4.5.
    _extension: Any = None

    def __post_init__(self):
        # Wrap the raw skeleton client in the access guard so that only
        # ``@ext.skeleton`` tool invocations (``_tool_type == "skeleton"``)
        # can read sections. Keep the wrapped client reachable via the
        # ``_raw_skeleton`` attribute for the as_user() rebuild path.
        self._raw_skeleton = self.skeleton
        if self.skeleton is not None:
            self.skeleton = _SkeletonAccessGuard(self.skeleton, self._tool_type)

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
            _tool_type=self._tool_type,
            _call_token=self._call_token,
            _extension=self._extension,
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
        # Use the raw (unwrapped) client so the new Context can wrap it with
        # its own guard + (possibly different) tool_type. ``_raw_skeleton``
        # is populated in ``__post_init__``. SkeletonClient stores its token
        # as ``_token`` (accepts both auth_token= and service_token=).
        raw = getattr(self, "_raw_skeleton", None) or self.skeleton
        return SkeletonClient(
            gateway_url=raw._gateway_url,
            service_token=raw._token,
            extension_id=self._extension_id,
            user_id=user_id,
            call_token=getattr(raw, "_call_token", ""),
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
