"""Shim — re-exports _check_target_scope for chat/extension.py backward compat."""
from __future__ import annotations

try:
    from imperal_kernel.pipeline.scope_guard import _check_target_scope  # noqa: F401
except ImportError:
    import logging as _log
    _log.getLogger(__name__).error("imperal_kernel not installed — _check_target_scope unavailable")

    def _check_target_scope(**kwargs):  # type: ignore[misc]
        return {"allowed": False, "reason": "imperal_kernel not installed"}
