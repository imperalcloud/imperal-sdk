"""
Pre-Flight BOM Extractor (RFC: ICNLI V17 / GNC Marathon Resilience Engine)

Scans target codebases (NodeJS: Express/Fastify/Koa/Next.js/HTML, Python: Flask/FastAPI/Django)
to extract a ground-truth Bill-of-Materials (BOM) before coding starts:
  - Screens and UI Pages (views, templates, React/Vue/Svelte/JSX components)
  - HTTP Routes & Endpoints (methods, paths, handlers)
  - Database Models (tables, schemas, entity relationships)
  - Services & Modules

Ingests the extracted BOM directly into Tenant Vault Working RAM as the Target State Vector X_target.
"""

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Set
from pathlib import Path


@dataclass
class BOMEntity:
    entity_id: str
    kind: str           # 'screen' | 'route' | 'model' | 'service' | 'module'
    name: str
    category: str = "core"
    source_file: str = ""
    status: str = "pending"
    maturity: float = 0.0
    spec: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BOMReport:
    project_id: str
    source_root: str
    total_screens: int
    total_routes: int
    total_models: int
    entities: List[BOMEntity] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "source_root": self.source_root,
            "total_screens": self.total_screens,
            "total_routes": self.total_routes,
            "total_models": self.total_models,
            "entities": [asdict(e) for e in self.entities]
        }


class BOMExtractor:
    """Extracts ground-truth system entities from legacy or target repositories."""

    def __init__(self, project_id: str = "wpanel"):
        self.project_id = project_id

    def extract_from_directory(self, target_dir: str) -> BOMReport:
        root = Path(target_dir).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Target directory '{target_dir}' does not exist.")

        entities: List[BOMEntity] = []
        seen_ids: Set[str] = set()

        # 1. Scan for Routes (Express/Fastify/Koa/HTTP handlers)
        route_patterns = [
            # app.get('/path', ...), router.post('/path', ...)
            re.compile(r"""(?:app|router|server)\.(get|post|put|delete|patch)\s*\(\s*['"`]([^'"`]+)['"`]""", re.IGNORECASE),
            # @router.get('/path'), @app.post('/path')
            re.compile(r"""@(app|router)\.(get|post|put|delete|patch)\s*\(\s*['"`]([^'"`]+)['"`]""", re.IGNORECASE),
        ]

        # 2. Scan for Screens / Pages / Views
        screen_exts = {".html", ".ejs", ".pug", ".hbs", ".jsx", ".tsx", ".vue", ".svelte"}

        # 3. Scan for DB Models (Sequelize, Prisma, Mongoose, TypeORM, SQLAlchemy)
        model_patterns = [
            re.compile(r"""sequelize\.define\s*\(\s*['"`]([^'"`]+)['"`]""", re.IGNORECASE),
            re.compile(r"""mongoose\.model\s*\(\s*['"`]([^'"`]+)['"`]""", re.IGNORECASE),
            re.compile(r"""class\s+(\w+)\s*\(.*(?:Base|Model|db\.Model).*\):"""),
            re.compile(r"""model\s+(\w+)\s*\{"""), # Prisma
        ]

        for current_path, dirs, files in os.walk(root):
            # Prune heavy/build directories
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", ".next", "dist", "build", "venv", "__pycache__"}]

            for f in files:
                file_path = Path(current_path) / f
                rel_path = str(file_path.relative_to(root))
                ext = file_path.suffix.lower()

                # Check for Screen
                if ext in screen_exts or "view" in rel_path.lower() or "page" in rel_path.lower() or "screen" in rel_path.lower():
                    # Deduce screen name
                    screen_name = file_path.stem
                    if screen_name in {"index", "page"} and file_path.parent != root:
                        screen_name = file_path.parent.name
                    
                    eid = f"screen_{screen_name.lower().replace('-', '_').replace(' ', '_')}"
                    if eid not in seen_ids:
                        seen_ids.add(eid)
                        category = self._categorize(screen_name, rel_path)
                        entities.append(BOMEntity(
                            entity_id=eid,
                            kind="screen",
                            name=screen_name.replace("_", " ").title(),
                            category=category,
                            source_file=rel_path,
                            spec={"relative_path": rel_path, "format": ext}
                        ))

                # Check for Routes & Models in text files
                if ext in {".js", ".mjs", ".ts", ".py", ".json"}:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue

                    # Routes extraction
                    for pat in route_patterns:
                        for match in pat.finditer(content):
                            groups = match.groups()
                            method = groups[0] if groups[0] in {"get", "post", "put", "delete", "patch"} else groups[1]
                            path = groups[-1]
                            rid = f"route_{method.lower()}_{path.strip('/').replace('/', '_').replace(':', 'by_') or 'root'}"
                            if rid not in seen_ids:
                                seen_ids.add(rid)
                                category = self._categorize(path, rel_path)
                                entities.append(BOMEntity(
                                    entity_id=rid,
                                    kind="route",
                                    name=f"{method.upper()} {path}",
                                    category=category,
                                    source_file=rel_path,
                                    spec={"method": method.upper(), "path": path}
                                ))

                    # Models extraction
                    for pat in model_patterns:
                        for match in pat.finditer(content):
                            mname = match.group(1)
                            mid = f"model_{mname.lower()}"
                            if mid not in seen_ids:
                                seen_ids.add(mid)
                                category = self._categorize(mname, rel_path)
                                entities.append(BOMEntity(
                                    entity_id=mid,
                                    kind="model",
                                    name=mname,
                                    category=category,
                                    source_file=rel_path,
                                    spec={"model_name": mname}
                                ))

        screens = [e for e in entities if e.kind == "screen"]
        routes = [e for e in entities if e.kind == "route"]
        models = [e for e in entities if e.kind == "model"]

        return BOMReport(
            project_id=self.project_id,
            source_root=str(root),
            total_screens=len(screens),
            total_routes=len(routes),
            total_models=len(models),
            entities=entities
        )

    def _categorize(self, name: str, path: str) -> str:
        s = (name + " " + path).lower()
        if any(k in s for k in ["site", "domain", "vhost", "web"]):
            return "websites"
        if any(k in s for k in ["db", "database", "mysql", "postgres", "sql"]):
            return "databases"
        if any(k in s for k in ["mail", "email", "forward", "spam"]):
            return "mail"
        if any(k in s for k in ["dns", "zone", "record"]):
            return "dns"
        if any(k in s for k in ["ssl", "cert", "tls", "encrypt"]):
            return "ssl"
        if any(k in s for k in ["file", "dir", "upload", "ftp"]):
            return "files"
        if any(k in s for k in ["backup", "snapshot", "restore"]):
            return "backups"
        if any(k in s for k in ["cron", "schedule", "task"]):
            return "cron"
        if any(k in s for k in ["user", "account", "profile", "auth", "login"]):
            return "auth_user"
        return "system"
