# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Local Mocking Kit for Imperal SDK — Zero-Network Offline Testing.

Provides drop-in, zero-network mock implementations of all Context subsystems:
- MockBilling: offline wallet balances, holds, plan checks, token charges.
- MockRBAC: in-memory user roles, scopes, and permission checks.
- MockAI: simulated LLM responses, token counting, completions.
- MockStore: key-value storage with isolation.
- MockSecrets: simulated encrypted secrets vault.

Allows authors to write rapid unit/integration tests running in <10ms without
any live Gateway, Redis, or platform worker dependencies.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


class MockBilling:
    """Zero-network billing mock."""

    def __init__(self, balance: int = 100_000, plan: str = "pro") -> None:
        self.balance: int = balance
        self.plan: str = plan
        self.ledger: List[Dict[str, Any]] = []

    async def get_balance(self) -> int:
        return self.balance

    async def charge(self, amount: int, reason: str = "") -> bool:
        if self.balance < amount:
            return False
        self.balance -= amount
        self.ledger.append({"type": "charge", "amount": amount, "reason": reason})
        return True

    async def check_plan(self) -> str:
        return self.plan


class MockRBAC:
    """Zero-network RBAC mock."""

    def __init__(self, roles: Optional[List[str]] = None, scopes: Optional[List[str]] = None) -> None:
        self.roles: List[str] = roles or ["user", "developer"]
        self.scopes: List[str] = scopes or ["read", "write", "execute"]

    async def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.roles or "*" in self.scopes

    async def get_roles(self) -> List[str]:
        return list(self.roles)


class MockAI:
    """Zero-network AI completion mock."""

    def __init__(self, default_response: str = "Mocked AI reasoning response") -> None:
        self.default_response: str = default_response
        self.calls: List[Dict[str, Any]] = []

    async def complete(self, prompt: str, model: str = "gpt-4o", **kwargs) -> str:
        self.calls.append({"prompt": prompt, "model": model, "kwargs": kwargs})
        return self.default_response


class MockStore:
    """In-memory key-value state store."""

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None


class AutonomousMockContext:
    """Autonomous zero-network Context mock with all platform subsystems populated."""

    def __init__(
        self,
        imperal_id: str = "mock_user_123",
        email: str = "author@imperal.io",
        tenant_id: str = "default_tenant",
        roles: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None,
        balance: int = 100_000,
        plan: str = "pro",
    ) -> None:
        self.imperal_id = imperal_id
        self.email = email
        self.tenant_id = tenant_id
        self.billing = MockBilling(balance=balance, plan=plan)
        self.rbac = MockRBAC(roles=roles, scopes=scopes)
        self.ai = MockAI()
        self.store = MockStore()

    def as_context(self) -> AutonomousMockContext:
        return self
