"""
Tenant Vault Working RAM Client (RFC: ICNLI V17 / GNC Marathon Resilience Engine)

Provides sub-3ms working memory access for autonomous marathons.
Separates LLM Reasoning Core (CPU/ALU) from Persistent State Store (Working RAM).
"""

from __future__ import annotations

import sqlite3
import json
import time
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path


@dataclass
class TargetEntity:
    entity_id: str
    project_id: str
    kind: str           # 'screen' | 'route' | 'model' | 'service' | 'module'
    name: str
    category: str = "core"
    status: str = "pending"  # 'pending' | 'scaffolded' | 'wired' | 'verified' | 'blocked'
    maturity: float = 0.0    # 0.0 to 1.0
    spec: Dict[str, Any] = field(default_factory=dict)
    dwell_steps: int = 0
    dwell_seconds: float = 0.0


@dataclass
class WorkingRAMSnapshot:
    project_id: str
    total_entities: int
    macro_coverage: float    # mean maturity [0.0 ... 1.0]
    entities: Dict[str, TargetEntity]
    active_blockers: List[Dict[str, Any]]
    proof_count: int


class TenantVaultRAM:
    """High-speed Tenant Vault Working RAM Client using embedded SQLite FTS5."""

    def __init__(self, db_path: Optional[str] = None, project_id: str = "default"):
        if db_path is None:
            vault_dir = os.environ.get("TENANT_VAULT_DIR", os.path.expanduser("~/.imperal/vault"))
            os.makedirs(vault_dir, exist_ok=True)
            db_path = os.path.join(vault_dir, f"working_ram_{project_id}.sqlite")
        
        self.db_path = db_path
        self.project_id = project_id
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        schema_path = Path(__file__).parent / "schema" / "marathon_ram.sql"
        if schema_path.exists():
            schema_sql = schema_path.read_text(encoding="utf-8")
        else:
            schema_sql = """
            CREATE TABLE IF NOT EXISTS ram_target_entities (
                entity_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'core',
                status TEXT NOT NULL DEFAULT 'pending',
                maturity REAL NOT NULL DEFAULT 0.0,
                spec_json TEXT NOT NULL DEFAULT '{}',
                dwell_steps INTEGER NOT NULL DEFAULT 0,
                dwell_seconds REAL NOT NULL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_ram_entities_project ON ram_target_entities(project_id);
            CREATE TABLE IF NOT EXISTS ram_contracts_index (
                contract_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                entity_id TEXT,
                symbol_name TEXT NOT NULL,
                symbol_type TEXT NOT NULL,
                input_schema TEXT NOT NULL DEFAULT '{}',
                output_schema TEXT NOT NULL DEFAULT '{}',
                hash_signature TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ram_proof_of_done (
                proof_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                entity_id TEXT,
                verification_type TEXT NOT NULL,
                evidence_payload TEXT NOT NULL,
                is_verified INTEGER NOT NULL DEFAULT 1,
                verified_by TEXT NOT NULL DEFAULT 'adversarial_oracle',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ram_blockers_scratchpad (
                blocker_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                source_entity_id TEXT,
                title TEXT NOT NULL,
                details TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'minor',
                status TEXT NOT NULL DEFAULT 'deferred',
                workaround_applied TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        with self._get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def ingest_bom(self, entities: List[Dict[str, Any]]) -> int:
        """Ingests a Bill-of-Materials (BOM) extracted from a target codebase."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        count = 0
        with self._get_connection() as conn:
            for item in entities:
                eid = item.get("id") or item.get("entity_id") or item["name"].lower().replace(" ", "_")
                conn.execute(
                    """
                    INSERT INTO ram_target_entities (entity_id, project_id, kind, name, category, status, maturity, spec_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id) DO UPDATE SET
                        name=excluded.name,
                        category=excluded.category,
                        spec_json=excluded.spec_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        eid,
                        self.project_id,
                        item.get("kind", "screen"),
                        item["name"],
                        item.get("category", "core"),
                        item.get("status", "pending"),
                        float(item.get("maturity", 0.0)),
                        json.dumps(item.get("spec", {})),
                        now
                    )
                )
                count += 1
            conn.commit()
        return count

    def update_maturity(self, entity_id: str, maturity: float, status: Optional[str] = None, dwell_delta: int = 1) -> None:
        """Updates maturity score [0.0..1.0] and increments dwell counters."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            if status:
                conn.execute(
                    """
                    UPDATE ram_target_entities
                    SET maturity = ?, status = ?, dwell_steps = dwell_steps + ?, updated_at = ?
                    WHERE entity_id = ? AND project_id = ?
                    """,
                    (max(0.0, min(1.0, float(maturity))), status, dwell_delta, now, entity_id, self.project_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE ram_target_entities
                    SET maturity = ?, dwell_steps = dwell_steps + ?, updated_at = ?
                    WHERE entity_id = ? AND project_id = ?
                    """,
                    (max(0.0, min(1.0, float(maturity))), dwell_delta, now, entity_id, self.project_id)
                )
            conn.commit()

    def get_snapshot(self) -> WorkingRAMSnapshot:
        """Computes the full macro completion vector and active blocker state."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM ram_target_entities WHERE project_id = ? ORDER BY name ASC",
                (self.project_id,)
            )
            rows = cur.fetchall()
            
            entities: Dict[str, TargetEntity] = {}
            total_mat = 0.0
            for r in rows:
                ent = TargetEntity(
                    entity_id=r["entity_id"],
                    project_id=r["project_id"],
                    kind=r["kind"],
                    name=r["name"],
                    category=r["category"],
                    status=r["status"],
                    maturity=float(r["maturity"]),
                    spec=json.loads(r["spec_json"]) if r["spec_json"] else {},
                    dwell_steps=int(r["dwell_steps"]),
                    dwell_seconds=float(r["dwell_seconds"])
                )
                entities[ent.entity_id] = ent
                total_mat += ent.maturity

            cur_blk = conn.execute(
                "SELECT * FROM ram_blockers_scratchpad WHERE project_id = ? AND status = 'deferred'",
                (self.project_id,)
            )
            blockers = [dict(b) for b in cur_blk.fetchall()]

            cur_p = conn.execute(
                "SELECT COUNT(*) as cnt FROM ram_proof_of_done WHERE project_id = ? AND is_verified = 1",
                (self.project_id,)
            )
            proof_cnt = cur_p.fetchone()["cnt"]

        total_cnt = len(entities)
        macro_cov = (total_mat / total_cnt) if total_cnt > 0 else 0.0
        return WorkingRAMSnapshot(
            project_id=self.project_id,
            total_entities=total_cnt,
            macro_coverage=macro_cov,
            entities=entities,
            active_blockers=blockers,
            proof_count=proof_cnt
        )

    def get_micro_slice(self, entity_id: str) -> Dict[str, Any]:
        """Returns minimal 4-8 KB context slice for the LLM ALU focus."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM ram_target_entities WHERE entity_id = ? AND project_id = ?",
                (entity_id, self.project_id)
            )
            row = cur.fetchone()
            if not row:
                return {}
            
            cur_c = conn.execute(
                "SELECT symbol_name, symbol_type, input_schema, output_schema FROM ram_contracts_index WHERE entity_id = ? AND project_id = ?",
                (entity_id, self.project_id)
            )
            contracts = [dict(c) for c in cur_c.fetchall()]

            cur_p = conn.execute(
                "SELECT verification_type, evidence_payload, timestamp FROM ram_proof_of_done WHERE entity_id = ? AND project_id = ?",
                (entity_id, self.project_id)
            )
            proofs = [dict(p) for p in cur_p.fetchall()]

        return {
            "entity": {
                "id": row["entity_id"],
                "name": row["name"],
                "kind": row["kind"],
                "category": row["category"],
                "status": row["status"],
                "maturity": float(row["maturity"]),
                "dwell_steps": int(row["dwell_steps"]),
                "spec": json.loads(row["spec_json"]) if row["spec_json"] else {}
            },
            "contracts": contracts,
            "verified_proofs": proofs
        }

    def commit_proof_of_done(self, entity_id: str, verification_type: str, evidence: str, verified_by: str = "adversarial_oracle") -> str:
        """Stores physical evidence of completion."""
        proof_id = f"proof_{time.time_ns()}_{entity_id}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ram_proof_of_done (proof_id, project_id, entity_id, verification_type, evidence_payload, is_verified, verified_by)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (proof_id, self.project_id, entity_id, verification_type, evidence, verified_by)
            )
            conn.commit()
        return proof_id

    def defer_blocker(self, title: str, details: str, source_entity_id: Optional[str] = None, workaround: Optional[str] = None) -> str:
        """Buffers non-critical blockers in the scratchpad to prevent recursive derailment."""
        bid = f"blk_{time.time_ns()}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ram_blockers_scratchpad (blocker_id, project_id, source_entity_id, title, details, workaround_applied)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (bid, self.project_id, source_entity_id, title, details, workaround)
            )
            conn.commit()
        return bid
