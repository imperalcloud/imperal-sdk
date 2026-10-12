"""
Cross-Surface Live Bus for Tenant Vault Working RAM (RFC: ICNLI V17)
Synchronizes marathon state, target vectors X(t), and focus shifts across:
  - Terminal (Webbee Code TUI)
  - Temporal Worker (Orchestration Engine)
  - Web Panel (Declarative UI / System Monitor)
  - Telegram (Agent Status Cards)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Callable


@dataclass
class MarathonLiveEvent:
    event_id: str
    project_id: str
    timestamp: float
    surface_source: str       # 'terminal' | 'worker' | 'panel' | 'telegram'
    event_type: str           # 'focus_shift' | 'maturity_update' | 'proof_committed' | 'limit_cycle_break' | 'blocker_deferred'
    entity_id: Optional[str] = None
    macro_coverage: float = 0.0
    payload: Dict[str, Any] = None


class CrossSurfaceLiveBus:
    """
    High-speed memory bus coordinating marathon state across all 4 surfaces.
    Pluggable backend: in-memory pubsub, Redis Stream, or SQLite Event WAL.
    """

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self._subscribers: List[Callable[[MarathonLiveEvent], None]] = []
        self._event_history: List[MarathonLiveEvent] = []

    def subscribe(self, callback: Callable[[MarathonLiveEvent], None]) -> None:
        """Register a cross-surface listener."""
        self._subscribers.append(callback)

    def publish(
        self,
        surface_source: str,
        event_type: str,
        entity_id: Optional[str] = None,
        macro_coverage: float = 0.0,
        payload: Optional[Dict[str, Any]] = None
    ) -> MarathonLiveEvent:
        """Broadcasts a live marathon transition to all surfaces."""
        event = MarathonLiveEvent(
            event_id=f"evt_{time.time_ns()}",
            project_id=self.project_id,
            timestamp=time.time(),
            surface_source=surface_source,
            event_type=event_type,
            entity_id=entity_id,
            macro_coverage=macro_coverage,
            payload=payload or {}
        )
        self._event_history.append(event)

        for sub in self._subscribers:
            try:
                sub(event)
            except Exception as e:
                # Surface errors must never crash the core bus
                pass

        return event

    def get_recent_events(self, limit: int = 50) -> List[MarathonLiveEvent]:
        """Returns the most recent cross-surface state mutations."""
        return self._event_history[-limit:]
