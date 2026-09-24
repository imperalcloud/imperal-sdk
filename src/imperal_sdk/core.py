# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the AGPL-3.0 License.
"""Universal ICNLI Core Primitives — Zero-dependency, pure stdlib, Python 3.6+ compatible.

Part of Foundation OS SDK:
- CancellationToken: Cooperative, thread-safe task cancellation.
- StreamEmitter: Real-time progress and stream chunk emitter for MCP & ICNLI agents.
- SchemaValidator: Zero-dep JSON Schema Draft 7 validator (types, required, enum).
- ICNLIComponent: Lightweight dictionary representations of Declarative UI components.
"""
from __future__ import annotations

import sys
import json
import time
import threading
from typing import Any, Dict, List, Optional, Callable


class CancellationToken:
    """Thread-safe cooperative cancellation token."""

    def __init__(self) -> None:
        self._cancelled: bool = False
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[], None]] = []

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def cancel(self) -> None:
        callbacks_to_fire: List[Callable[[], None]] = []
        with self._lock:
            if not self._cancelled:
                self._cancelled = True
                callbacks_to_fire = list(self._callbacks)
        for cb in callbacks_to_fire:
            try:
                cb()
            except Exception:
                pass

    def on_cancelled(self, callback: Callable[[], None]) -> None:
        with self._lock:
            if self._cancelled:
                fire = True
            else:
                self._callbacks.append(callback)
                fire = False
        if fire:
            try:
                callback()
            except Exception:
                pass


class StreamEmitter:
    """Streams JSON-RPC / MCP / ICNLI events to standard output with immediate flush."""

    def __init__(self, out_stream: Optional[Any] = None) -> None:
        self._stream = out_stream if out_stream is not None else sys.stdout
        self._lock = threading.Lock()

    def emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        message = {
            "type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }
        raw = json.dumps(message, ensure_ascii=False)
        with self._lock:
            self._stream.write(raw + "\n")
            self._stream.flush()

    def emit_progress(self, percent: float, message: str = "") -> None:
        pct = max(0.0, min(100.0, float(percent)))
        self.emit_event("progress", {"percent": pct, "message": str(message)})

    def emit_chunk(self, chunk: str, stream_name: str = "stdout") -> None:
        self.emit_event("stream_chunk", {"chunk": str(chunk), "stream": str(stream_name)})


class SchemaValidator:
    """Pure stdlib JSON Schema Draft 7 validator (types, required, enum)."""

    @staticmethod
    def validate(instance: Any, schema: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not isinstance(schema, dict):
            return errors

        expected_type = schema.get("type")
        if expected_type:
            type_map = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            if expected_type == "integer" and isinstance(instance, bool):
                errors.append(f"Expected type 'integer', got boolean")
            elif expected_type in type_map:
                target_cls = type_map[expected_type]
                if not isinstance(instance, target_cls):
                    errors.append(f"Expected type '{expected_type}', got {type(instance).__name__}")

        if "enum" in schema and isinstance(schema["enum"], list):
            if instance not in schema["enum"]:
                errors.append(f"Value {instance!r} is not in enum {schema['enum']}")

        if isinstance(instance, dict):
            required = schema.get("required", [])
            for req in required:
                if req not in instance:
                    errors.append(f"Missing required property '{req}'")

            props = schema.get("properties", {})
            for k, val in instance.items():
                if k in props:
                    sub_errs = SchemaValidator.validate(val, props[k])
                    for se in sub_errs:
                        errors.append(f"Property '{k}': {se}")

        return errors


class ICNLIComponent:
    """Constructs zero-dependency JSON-compatible ICNLI UI representations."""

    @staticmethod
    def entity_list(items: List[Dict[str, Any]], total_count: int, omitted_count: int = 0) -> Dict[str, Any]:
        return {
            "component": "EntityList",
            "items": list(items),
            "shown": len(items),
            "total": int(total_count),
            "omitted": int(omitted_count),
        }

    @staticmethod
    def confirmation_gate(operation: str, affected_entities: List[str], risk_level: str = "destructive") -> Dict[str, Any]:
        return {
            "component": "ConfirmationGate",
            "operation": str(operation),
            "affected": list(affected_entities),
            "affected_count": len(affected_entities),
            "risk": str(risk_level),
        }

    @staticmethod
    def stat_card(label: str, value: Any, delta: Optional[str] = None, status: str = "normal") -> Dict[str, Any]:
        res = {
            "component": "StatCard",
            "label": str(label),
            "value": value,
            "status": str(status),
        }
        if delta is not None:
            res["delta"] = str(delta)
        return res
