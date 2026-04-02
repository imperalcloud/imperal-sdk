# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from dataclasses import dataclass, field


@dataclass
class User:
    id: str
    email: str = ""
    tenant_id: str = "default"
    org_id: str | None = None
    role: str = "user"
    scopes: list[str] = field(default_factory=list)

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
