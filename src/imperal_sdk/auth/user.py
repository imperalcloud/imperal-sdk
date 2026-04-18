# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class User:
    id: str
    email: str = ""
    tenant_id: str = "default"
    # Agency multi-tenancy (rollout 2026-04-18). None during rollout for legacy
    # users; backfill + enforcement will follow. Extensions SHOULD forward this
    # value to downstream services (Cases API, etc.) via
    # `X-Imperal-Agency-ID: {ctx.user.agency_id or 'default'}`.
    agency_id: str | None = None
    org_id: str | None = None
    role: str = "user"
    scopes: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    is_active: bool = True

    def has_scope(self, scope: str) -> bool:
        if "*" in self.scopes:
            return True
        for s in self.scopes:
            if s == scope:
                return True
            if s.endswith(".*"):
                prefix = s[:-2]
                if scope.startswith(prefix + ".") or scope == prefix:
                    return True
        return False

    def has_role(self, role: str) -> bool:
        """Check if user has the specified role."""
        return self.role == role


@dataclass
class Tenant:
    """Tenant/organization info."""
    id: str
    name: str = ""
    plan: str = ""
    attributes: dict = field(default_factory=dict)
