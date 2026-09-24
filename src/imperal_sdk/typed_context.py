# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Typed Context & TypeGuards for Imperal SDK — IDE Autocompletion & Type Safety.

Provides TypeGuard helpers and TypedContext interfaces so developer IDEs
(VS Code, PyCharm) offer instant, rich autocompletion across all context namespaces:
- ctx.user: UserContext (imperal_id, email, tenant_id, role, scopes)
- ctx.billing: BillingContext (wallet, holds, token rate)
- ctx.store: StateStoreContext
- ctx.secrets: SecretsContext
- ctx.ai: AIModelContext
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypeGuard, Union, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from imperal_sdk.context import Context


class TypedUserContext(BaseModel):
    """Strongly typed User Context model."""
    imperal_id: str = Field(..., description="Unique user identifier")
    email: str = Field(..., description="User email address")
    tenant_id: str = Field(default="default", description="Tenant / Agency ID")
    role: str = Field(default="user", description="Primary RBAC role")
    scopes: List[str] = Field(default_factory=list, description="Assigned authorization scopes")


class TypedBillingContext(BaseModel):
    """Strongly typed Billing Context model."""
    balance: int = Field(default=0, description="Available token balance")
    plan: str = Field(default="free", description="Active subscription plan")
    holds: int = Field(default=0, description="Active balance holds")


def is_admin_context(ctx: Any) -> bool:
    """TypeGuard to verify if caller possesses administrative privileges."""
    user = getattr(ctx, "user", None)
    if not user:
        return False
    role = getattr(user, "role", "")
    scopes = getattr(user, "scopes", [])
    return role == "admin" or "admin:write" in scopes or "*" in scopes


def has_scope(ctx: Any, required_scope: str) -> bool:
    """TypeGuard to check if context carries a specific permission scope."""
    user = getattr(ctx, "user", None)
    if not user:
        return False
    scopes = getattr(user, "scopes", [])
    role = getattr(user, "role", "")
    if role == "admin" or "*" in scopes:
        return True
    return required_scope in scopes
