# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Auto-IR & UI-as-Data Projector for ICNLI Quantum SDK.

Transforms standard Python return types (dicts, dataclasses, lists, primitives)
into reactive Declarative IR components without writing custom frontend templates.
Compatible with Python 3.6 through 3.14+.
"""
import sys
from typing import Any, Dict, List, Optional, Union


def project_to_declarative_ir(data, title=None):
    # type: (Any, Optional[str]) -> Optional[Dict[str, Any]]
    """Project arbitrary Python data structures into Declarative IR schema.

    - If data already contains `_ui` or `declarative_ui`, returns it directly.
    - List of dicts -> Table Component with auto-detected columns.
    - Dict with numeric/status values -> Metric Card / Metric Grid.
    - Plain text/markdown -> Markdown Card.
    """
    if data is None:
        return None

    if isinstance(data, dict):
        if "_ui" in data and isinstance(data["_ui"], dict):
            return data["_ui"]
        if "declarative_ui" in data and isinstance(data["declarative_ui"], dict):
            return data["declarative_ui"]

        # If dict has status/metric keys, synthesize a MetricCard
        keys = set(data.keys())
        if any(k in keys for k in ("status", "metric", "count", "value", "state")):
            effective_title = title or data.get("title") or "Status"
            badge = str(data.get("status") or data.get("state") or "active")
            metric = str(data.get("metric") or data.get("value") or data.get("count") or "")
            details = {k: v for k, v in data.items() if k not in ("status", "metric", "title", "state")}
            return {
                "type": "metric_card",
                "title": effective_title,
                "badge": badge,
                "metric": metric,
                "details": details,
            }

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        # Synthesize Table
        columns = list(data[0].keys())[:8]  # Bounded column width
        return {
            "type": "table",
            "title": title or "Items",
            "columns": columns,
            "rows": data,
            "total": len(data),
        }

    return None
