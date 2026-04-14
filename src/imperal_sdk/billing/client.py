# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
import httpx

from imperal_sdk.types.models import BalanceInfo

log = logging.getLogger(__name__)


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
        return bool(self.exceeded)


@dataclass
class SubscriptionInfo:
    plan: str
    status: str
    started_at: str | None = None
    expires_at: str | None = None


class BillingClient:
    """Read-only billing client for extensions.

    When initialized with service_token (kernel context), uses internal
    endpoints with X-Service-Token header. When initialized with auth_token
    (user JWT from Panel), uses public endpoints with Authorization header.
    """

    def __init__(
        self, gateway_url: str, auth_token: str = "",
        service_token: str = "", user_id: str = "",
    ):
        self._gateway_url = gateway_url.rstrip("/")
        self._service_token = service_token
        self._auth_token = auth_token
        self._user_id = user_id

    def _headers(self) -> dict:
        if self._service_token:
            return {"X-Service-Token": self._service_token}
        return {"Authorization": f"Bearer {self._auth_token}"}

    def _uid(self, user: Any = None) -> str:
        return self._user_id or (getattr(user, "id", "") if user else "")

    async def check_limits(self, user: Any = None) -> LimitsResult:
        uid = self._uid(user)
        try:
            async with httpx.AsyncClient() as client:
                if self._service_token and uid:
                    resp = await client.get(
                        f"{self._gateway_url}/v1/billing/internal/user-limits/{uid}",
                        headers=self._headers(), timeout=10)
                else:
                    resp = await client.get(
                        f"{self._gateway_url}/v1/billing/usage",
                        headers=self._headers(), timeout=10)
                resp.raise_for_status()
                data = resp.json()
                return LimitsResult(
                    plan=data.get("plan", "free"),
                    usage=data.get("usage", {}),
                    limits=data.get("limits", {}),
                    exceeded=data.get("exceeded", []),
                )
        except Exception as e:
            log.warning("Billing check_limits failed: %s", e)
            return LimitsResult(plan="unknown", usage={}, limits={}, exceeded=[])

    async def get_subscription(self, user: Any = None) -> SubscriptionInfo:
        uid = self._uid(user)
        try:
            async with httpx.AsyncClient() as client:
                if self._service_token and uid:
                    resp = await client.get(
                        f"{self._gateway_url}/v1/billing/internal/subscription/{uid}",
                        headers=self._headers(), timeout=10)
                else:
                    resp = await client.get(
                        f"{self._gateway_url}/v1/billing/subscription",
                        headers=self._headers(), timeout=10)
                resp.raise_for_status()
                data = resp.json()
                return SubscriptionInfo(
                    plan=data.get("plan", "free"),
                    status=data.get("status", "unknown"),
                    started_at=data.get("started_at"),
                    expires_at=data.get("expires_at"),
                )
        except Exception as e:
            log.warning("Billing get_subscription failed: %s", e)
            return SubscriptionInfo(plan="unknown", status="unavailable")

    async def track_usage(self, meter: str, amount: int = 1, user: Any = None) -> bool:
        """Track usage for a given meter. Returns True on success."""
        uid = self._uid(user)
        try:
            async with httpx.AsyncClient() as client:
                payload = {"meter": meter, "amount": amount}
                if self._service_token and uid:
                    payload["user_id"] = uid
                    payload["tenant_id"] = "default"
                    resp = await client.post(
                        f"{self._gateway_url}/v1/billing/internal/usage/track",
                        json=payload, headers=self._headers(), timeout=10)
                else:
                    resp = await client.post(
                        f"{self._gateway_url}/v1/billing/usage/track",
                        json=payload, headers=self._headers(), timeout=10)
                return resp.status_code == 200
        except Exception as e:
            log.warning("Billing track_usage failed: %s", e)
            return False

    async def get_balance(self, user: Any = None) -> BalanceInfo:
        """Get current token balance and plan cap."""
        uid = self._uid(user)
        try:
            async with httpx.AsyncClient() as client:
                if self._service_token and uid:
                    resp = await client.get(
                        f"{self._gateway_url}/v1/billing/internal/balance/{uid}",
                        headers=self._headers(), timeout=10)
                else:
                    resp = await client.get(
                        f"{self._gateway_url}/v1/billing/balance",
                        headers=self._headers(), timeout=10)
                resp.raise_for_status()
                data = resp.json()
                return BalanceInfo(
                    balance=data.get("balance", 0),
                    plan=data.get("plan", ""),
                    cap=data.get("cap", 0),
                )
        except Exception as e:
            log.warning("Billing get_balance failed: %s", e)
            return BalanceInfo(balance=0, plan="unknown", cap=0)
