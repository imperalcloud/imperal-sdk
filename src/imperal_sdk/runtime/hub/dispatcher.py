# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Hub dispatcher — single extension dispatch."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from imperal_sdk.runtime.kernel_context import KernelContext as _KernelContext

log = logging.getLogger(__name__)


async def _dispatch_one(kctx: _KernelContext, app_id: str, tool_name: str, message: str,
                        history: list, skeleton: dict, context: dict,
                        chain_mode: bool = False, suppress_promotion: bool = False,
                        confirmation_bypassed: bool = False, chain_id: str = None) -> dict:
    """Dispatch to a single extension via _execute_extension (direct, no re-resolution)."""
    try:
        from imperal_sdk.runtime.executor import _execute_extension
        return await _execute_extension(
            kctx=kctx,
            app_id=app_id,
            tool_name=tool_name,
            message=message,
            history=history,
            skeleton=skeleton,
            context=context,
            chain_mode=chain_mode,
            suppress_promotion=suppress_promotion,
            confirmation_bypassed=confirmation_bypassed,
            chain_id=chain_id,
        )
    except Exception as e:
        log.error(f"Hub dispatch error {app_id}/{tool_name}: {e}")
        return {"response": "An error occurred while processing your request.", "_handled": False}
