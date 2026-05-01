"""Shim — re-exports _check_target_scope for chat/extension.py backward compat.

When imperal_kernel is not installed (SDK running standalone, e.g. in unit
tests), the fallback returns a complete dict shape (matching the kernel
implementation) so caller dict accesses like ``_tsg["target_user_id"]`` do
not raise KeyError. The fallback is intentionally permissive on shape but
restrictive on outcome (``allowed=False``).
"""
from __future__ import annotations

try:
    from imperal_kernel.pipeline.scope_guard import _check_target_scope  # noqa: F401
except ImportError:
    import logging as _log
    _log.getLogger(__name__).warning(
        "imperal_kernel not installed — _check_target_scope unavailable; "
        "SDK-standalone fallback in use (allowed=False, no scope checks)"
    )

    def _check_target_scope(**kwargs):  # type: ignore[misc]
        """SDK-standalone fallback. Returns complete dict shape."""
        return {
            "allowed": False,
            "reason": "imperal_kernel not installed",
            "target_user_id": "",
            "required_scope": "",
            "force_confirmation": False,
            "cross_user": False,
            "verdict": "no_kernel_fallback",
        }
