"""Bounded, non-Turing canon projection for IR entity descriptors."""
from __future__ import annotations

from typing import Any


def _first_present(fields: list[str], data: dict) -> Any:
    for f in fields:
        v = data.get(f)
        if v is not None:
            return v
    return ""


def project_canon(spec: dict, data: dict) -> dict:
    """Return canonical {id?, title?, kind?} fields from *data* using *spec*.

    Currently implemented: ``id_from`` — a list of field names tried in order;
    first non-None value wins; empty string ``""`` if none match.

    ``kind_const`` and ``title_template`` are reserved for the C5 task and are
    intentionally absent here (YAGNI).
    """
    out: dict[str, Any] = {}
    if "id_from" in spec:
        out["id"] = _first_present(list(spec["id_from"]), data)
    return out
