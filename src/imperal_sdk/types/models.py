"""Data types returned by SDK clients.

These are the typed return values from StoreProtocol, AIProtocol,
BillingProtocol, StorageProtocol, and HTTPProtocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Document:
    """A document in the extension store."""
    id: str
    collection: str
    data: dict
    extension_id: str = ""
    tenant_id: str = "default"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CompletionResult:
    """Result from ctx.ai.complete()."""
    text: str
    model: str = ""
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""


@dataclass
class LimitsResult:
    """Result from ctx.billing.check_limits()."""
    allowed: bool = True
    balance: int = 0
    plan: str = ""
    limits: dict = field(default_factory=dict)
    message: str = ""


@dataclass
class SubscriptionInfo:
    """Result from ctx.billing.get_subscription()."""
    plan_id: str = ""
    plan_name: str = ""
    status: str = ""
    period: str = "monthly"
    current_period_start: str = ""
    current_period_end: str = ""


@dataclass
class BalanceInfo:
    """Result from ctx.billing.get_balance()."""
    balance: int = 0
    plan: str = ""
    cap: int = 0


@dataclass
class FileInfo:
    """Result from ctx.storage.upload() and ctx.storage.list()."""
    path: str
    size: int = 0
    content_type: str = ""
    created_at: str = ""
    url: str = ""


@dataclass
class HTTPResponse:
    """Result from ctx.http.get/post/put/patch/delete()."""
    status_code: int
    body: dict | str | bytes = ""
    headers: dict = field(default_factory=dict)

    def json(self) -> dict:
        if isinstance(self.body, dict):
            return self.body
        if isinstance(self.body, str):
            import json
            return json.loads(self.body)
        raise ValueError("Body is bytes, cannot parse as JSON")

    def text(self) -> str:
        if isinstance(self.body, str):
            return self.body
        if isinstance(self.body, bytes):
            return self.body.decode("utf-8")
        import json
        return json.dumps(self.body)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300
