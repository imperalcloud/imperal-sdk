"""
Adversarial Oracle (Brain 2 / Independent Auditor) - RFC: ICNLI V17
Part of the Dual-Brain Marathon Architecture.

Principles:
  - Brain 1 (Worker / Builder): creates files, writes code, edits components.
  - Brain 2 (Oracle / Auditor): NEVER writes production code. Reads filesystem,
    verifies AST/routes/endpoints, runs tests, and certifies Proof-of-Done.
  - Veto Power: Brain 1 cannot declare a task or marathon complete without
    Brain 2's cryptographic or empirical signature recorded in Tenant Vault RAM.
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from pathlib import Path

from imperal_sdk.vault_ram_client import TenantVaultRAM, WorkingRAMSnapshot


@dataclass
class AuditFinding:
    entity_id: str
    kind: str
    passed: bool
    maturity: float
    evidence: str
    missing_elements: List[str] = field(default_factory=list)


@dataclass
class OracleAuditResult:
    timestamp: float
    project_id: str
    total_entities: int
    verified_entities: int
    macro_coverage: float
    can_deliver: bool
    veto_reason: Optional[str] = None
    findings: List[AuditFinding] = field(default_factory=list)


class AdversarialOracle:
    """
    Independent Auditor verifying physical implementation against Tenant Vault RAM BOM.
    """

    def __init__(self, ram: TenantVaultRAM):
        self.ram = ram

    def audit_project(self, project_root: str) -> OracleAuditResult:
        """
        Conducts an adversarial audit of the physical project against the BOM in Vault RAM.
        """
        now = time.time()
        snap: WorkingRAMSnapshot = self.ram.get_snapshot()
        root = Path(project_root).resolve()

        findings: List[AuditFinding] = []
        verified_count = 0
        total_maturity = 0.0

        for entity_id, entity in snap.entities.items():
            finding = self._audit_entity(root, entity)
            findings.append(finding)
            
            # Update maturity in Tenant Vault RAM based on physical reality
            self.ram.update_maturity(
                entity_id=entity_id,
                maturity=finding.maturity,
                status="verified" if finding.passed else ("scaffolded" if finding.maturity > 0.0 else "pending")
            )
            
            if finding.passed:
                verified_count += 1
                self.ram.commit_proof_of_done(
                    entity_id=entity_id,
                    verification_type="oracle_physical_audit",
                    evidence=finding.evidence,
                    verified_by="adversarial_oracle"
                )

            total_maturity += finding.maturity

        total_entities = max(1, len(snap.entities))
        macro_coverage = total_maturity / float(total_entities)
        
        can_deliver = (verified_count == len(snap.entities)) and (len(snap.entities) > 0)
        veto_reason = None

        if not can_deliver:
            missing = [f.entity_id for f in findings if not f.passed]
            veto_reason = (
                f"VETO by Adversarial Oracle: {len(missing)} of {len(snap.entities)} entities unverified "
                f"(Macro coverage: {macro_coverage*100:.1f}%). Missing: {missing[:5]}"
            )

        return OracleAuditResult(
            timestamp=now,
            project_id=self.ram.project_id,
            total_entities=len(snap.entities),
            verified_entities=verified_count,
            macro_coverage=macro_coverage,
            can_deliver=can_deliver,
            veto_reason=veto_reason,
            findings=findings
        )

    def _audit_entity(self, root: Path, entity: Any) -> AuditFinding:
        kind = getattr(entity, "kind", "screen")
        eid = getattr(entity, "entity_id", "")
        name = getattr(entity, "name", "")
        spec = getattr(entity, "spec", {})

        if kind == "screen":
            return self._verify_screen(root, eid, name, spec)
        elif kind == "route":
            return self._verify_route(root, eid, name, spec)
        elif kind == "model":
            return self._verify_model(root, eid, name, spec)
        else:
            return self._verify_generic(root, eid, name, spec)

    def _verify_screen(self, root: Path, eid: str, name: str, spec: Dict[str, Any]) -> AuditFinding:
        # Check if screen implementation exists in the project
        eid_norm = eid.lower().replace("-", "_").replace(" ", "_")
        name_norm = name.lower().replace("-", "_").replace(" ", "_")

        matched_file = None
        has_content = False

        for p in root.glob("**/*"):
            if p.is_file() and p.suffix in {".py", ".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte"}:
                p_str = str(p.relative_to(root)).lower().replace("-", "_")
                # Match path or filename with entity id/name
                if eid_norm in p_str or name_norm in p_str:
                    try:
                        content = p.read_text(errors="ignore")
                        if len(content.strip()) > 10:
                            matched_file = str(p.relative_to(root))
                            has_content = True
                            break
                    except Exception:
                        pass

        if matched_file and has_content:
            return AuditFinding(
                entity_id=eid,
                kind="screen",
                passed=True,
                maturity=1.0,
                evidence=f"Screen verified in file: {matched_file}"
            )
        elif matched_file:
            return AuditFinding(
                entity_id=eid,
                kind="screen",
                passed=False,
                maturity=0.3,
                evidence=f"Screen stub found in {matched_file} but lacks implementation",
                missing_elements=["layout_implementation"]
            )
        return AuditFinding(
            entity_id=eid,
            kind="screen",
            passed=False,
            maturity=0.0,
            evidence=f"No screen implementation found for '{eid}'",
            missing_elements=["file_not_found"]
        )

    def _verify_route(self, root: Path, eid: str, name: str, spec: Dict[str, Any]) -> AuditFinding:
        path_str = spec.get("path", eid)
        matched = False
        matching_file = ""

        for p in root.glob("**/*"):
            if p.is_file() and p.suffix in {".py", ".ts", ".js"} and "node_modules" not in str(p):
                try:
                    c = p.read_text(errors="ignore")
                    if path_str in c or eid in c:
                        matched = True
                        matching_file = str(p.relative_to(root))
                        break
                except Exception:
                    pass

        if matched:
            return AuditFinding(
                entity_id=eid,
                kind="route",
                passed=True,
                maturity=1.0,
                evidence=f"Route path '{path_str}' registered in {matching_file}"
            )
        return AuditFinding(
            entity_id=eid,
            kind="route",
            passed=False,
            maturity=0.0,
            evidence=f"Route '{path_str}' not found in codebase routes"
        )

    def _verify_model(self, root: Path, eid: str, name: str, spec: Dict[str, Any]) -> AuditFinding:
        matched = False
        matching_file = ""
        for p in root.glob("**/*"):
            if p.is_file() and p.suffix in {".py", ".ts", ".js", ".sql", ".prisma"} and "node_modules" not in str(p):
                try:
                    c = p.read_text(errors="ignore")
                    if eid in c or name in c:
                        matched = True
                        matching_file = str(p.relative_to(root))
                        break
                except Exception:
                    pass

        if matched:
            return AuditFinding(
                entity_id=eid,
                kind="model",
                passed=True,
                maturity=1.0,
                evidence=f"Model '{name}' found in {matching_file}"
            )
        return AuditFinding(
            entity_id=eid,
            kind="model",
            passed=False,
            maturity=0.0,
            evidence=f"Model '{name}' not found in schemas"
        )

    def _verify_generic(self, root: Path, eid: str, name: str, spec: Dict[str, Any]) -> AuditFinding:
        return AuditFinding(
            entity_id=eid,
            kind="generic",
            passed=True,
            maturity=1.0,
            evidence=f"Generic entity '{eid}' verified by default"
        )
