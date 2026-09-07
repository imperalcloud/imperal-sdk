"""Imperal SDK · Semantic Omnisearch Protocol.

Allows extensions to declare semantic search capabilities.
By decorating a search handler with ``@ext.search_provider``, an extension
exposes searchable domain entities (e.g. customers, tasks, emails, repos)
to the OS-level semantic search engine (Cmd+K).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class SearchEntityResult:
    """Individual entity match returned by a search provider."""
    id: str
    title: str
    type: str  # e.g. 'customer', 'task', 'repo', 'transaction'
    snippet: str = ""
    score: float = 1.0
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "snippet": self.snippet,
            "score": self.score,
            "url": self.url,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class SearchProviderDef:
    """Declaration of a semantic search provider for an extension."""
    entity_type: str
    func: Callable
    description: str = ""

    def to_manifest(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "handler": getattr(self.func, "__name__", str(self.func)),
            "description": self.description,
        }
