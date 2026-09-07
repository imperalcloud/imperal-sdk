"""Imperal SDK · Signals Protocol and In-Process Client.

Allows emitting and subscribing to reactive state signals.
Used by ``ctx.signals.emit(key, value, **metadata)``.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine


class SignalsClient:
    """Reactive signal client attached to Context (ctx.signals)."""

    def __init__(self, gateway_url: str = "", service_token: str = ""):
        self._gateway_url = gateway_url.rstrip("/") if gateway_url else ""
        self._service_token = service_token
        self._local_subscribers: dict[str, list[Callable[[str, Any], Coroutine[Any, Any, None]]]] = {}

    async def emit(self, key: str, value: Any, **metadata) -> dict[str, Any]:
        """Emit a reactive state change for a key.

        Notifies any local in-process subscribers and broadcasts to the
        Imperal reactive event bus via gateway SSE/WebSocket.
        """
        payload = {
            "key": str(key),
            "value": value,
            "metadata": metadata,
        }

        # Dispatch locally if subscribers exist in-process
        callbacks = self._local_subscribers.get(str(key), [])
        for cb in callbacks:
            try:
                res = cb(str(key), value)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

        # If gateway is configured, post to signals endpoint
        if self._gateway_url:
            from imperal_sdk._shared_http import shared_http
            headers = {"Authorization": f"Bearer {self._service_token}"} if self._service_token else {}
            try:
                async with shared_http() as client:
                    await client.post(
                        f"{self._gateway_url}/api/v1/signals/emit",
                        json=payload,
                        headers=headers,
                        timeout=5.0,
                    )
            except Exception:
                # Signal emission is non-fatal; state best-effort propagates
                pass

        return {"ok": True, "key": key}

    def subscribe(self, key: str, callback: Callable[[str, Any], Coroutine[Any, Any, None]]):
        """Subscribe to in-process signal changes (for testing or real-time handlers)."""
        self._local_subscribers.setdefault(str(key), []).append(callback)
