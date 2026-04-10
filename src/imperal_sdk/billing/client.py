# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import httpx

from imperal_sdk.types.models import BalanceInfo


@dataclass
class LimitsResult:
    plan: str
    usage: dict[str, int]
    limits: dict[str, int]
    exceeded: list[str]

    def is_exceeded(self, meter: str) -> bool:
        return meter in self.exceeded

    @property
    def any_exceeded(self) -> bool:
        return len(self.exceeded) > 0


@dataclass
class SubscriptionInfo:
    plan: str
    status: str
    started_at: str | None = None
    expires_at: str | None = None


class BillingClient:
    """Read-only billing client for extensions."""

    def __init__(self, gateway_url: str, auth_token: str = "", service_token: str = ""):
        self._gateway_url = gateway_url.rstrip("/")
        self._auth_token = auth_token or service_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth_token}"}

    async def check_limits(self, user: Any = None) -> LimitsResult:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._gateway_url}/v1/billing/usage", headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return LimitsResult(plan=data["plan"], usage=data["usage"], limits=data["limits"], exceeded=data["exceeded"])

    async def get_subscription(self, user: Any = None) -> SubscriptionInfo:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._gateway_url}/v1/billing/subscription", headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return SubscriptionInfo(**resp.json())

    async def track_usage(self, meter: str, amount: int = 1, user: Any = None) -> bool:
        """Track usage for a given meter. Returns True on success."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._gateway_url}/v1/billing/usage/track", json={"meter": meter, "amount": amount}, headers=self._headers(), timeout=10)
            return resp.status_code == 200

    async def get_balance(self, user: Any = None) -> BalanceInfo:
        """Get current token balance and plan cap."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._gateway_url}/v1/billing/balance", headers=self._headers(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return BalanceInfo(balance=data.get("balance", 0), plan=data.get("plan", ""), cap=data.get("cap", 0))
