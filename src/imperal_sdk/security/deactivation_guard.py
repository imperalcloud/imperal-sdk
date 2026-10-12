"""
Deactivation & Ingress Security Guard (I-DEACTIVATED-USER-GUARD)
RFC / ICNLI Security Standard for AI Cloud OS.

Guards against resurrection of terminated sessions and workflows (e.g., personal-<imperal_id>)
via ingress signals such as Temporal SignalWithStart, Telegram webhooks, and gateway dispatches.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("imperal_sdk.security.deactivation_guard")


class DeactivatedUserBlockedException(Exception):
    """Raised when an ingress signal or workflow start is attempted for a deactivated user."""
    def __init__(self, imperal_id: str, reason: str = "User is deactivated"):
        self.imperal_id = imperal_id
        self.reason = reason
        super().__init__(f"I-DEACTIVATED-USER-GUARD: Blocked operation for '{imperal_id}': {reason}")


class DeactivationGuard:
    """
    Ingress and workflow boundary guard enforcing invariant I-DEACTIVATED-USER-GUARD.
    Prevents zombie workflow resurrection via SignalWithStart or webhook triggers.
    """

    def __init__(self, redis_client: Optional[Any] = None, temporal_client: Optional[Any] = None) -> None:
        self.redis = redis_client
        self.temporal = temporal_client
        self._local_blacklist: Set[str] = set()

    def add_to_blacklist(self, imperal_id: str) -> None:
        """Add user to in-memory blacklist and persistent Redis blacklist if available."""
        self._local_blacklist.add(imperal_id)
        if self.redis is not None:
            try:
                self.redis.sadd("imperal:blacklist:deactivated", imperal_id)
                self.redis.hset(f"imperal:user:{imperal_id}", "is_active", "0")
            except Exception as e:
                logger.error("Failed to sync blacklist to redis for %s: %s", imperal_id, e)

    def is_user_active(self, imperal_id: str) -> bool:
        """
        Check if user is active. Returns False if blacklisted or marked inactive in Redis.
        """
        if imperal_id in self._local_blacklist:
            return False

        if self.redis is not None:
            try:
                if self.redis.sismember("imperal:blacklist:deactivated", imperal_id):
                    self._local_blacklist.add(imperal_id)
                    return False
                active_val = self.redis.hget(f"imperal:user:{imperal_id}", "is_active")
                if active_val is not None:
                    # active_val may be bytes or str or int
                    if str(active_val).strip() in ("0", "false", "False", "b'0'"):
                        self._local_blacklist.add(imperal_id)
                        return False
            except Exception as e:
                logger.error("Redis error while checking active status for %s: %s", imperal_id, e)

        return True

    def verify_ingress_signal(self, imperal_id: str, signal_name: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """
        Pre-dispatch gate for ingress routers.
        Must be called BEFORE Temporal SignalWithStart or workflow signal dispatch.
        Raises DeactivatedUserBlockedException if user is deactivated.
        """
        if not self.is_user_active(imperal_id):
            logger.warning(
                "SECURITY ALERT [I-DEACTIVATED-USER-GUARD]: Blocked signal '%s' to personal-%s",
                signal_name, imperal_id
            )
            raise DeactivatedUserBlockedException(
                imperal_id=imperal_id,
                reason=f"Attempted signal '{signal_name}' on deactivated user workflow personal-{imperal_id}"
            )
        return True

    def cascade_deactivate_user(self, imperal_id: str, reason: str = "Administrative deactivation") -> Dict[str, Any]:
        """
        Execute full deactivation cascade:
        1. Add imperal_id to blacklist.
        2. Set is_active = False in Redis identity cache.
        3. Clear Redis session keys and Telegram binds.
        4. Terminate running Temporal workflows (personal-<imperal_id>).
        """
        self.add_to_blacklist(imperal_id)
        cleared_keys: List[str] = []
        workflow_terminated: bool = False

        if self.redis is not None:
            try:
                # Mark inactive in user record
                self.redis.hset(f"imperal:user:{imperal_id}", "is_active", "0")
                self.redis.hset(f"imperal:user:{imperal_id}", "deactivation_reason", reason)

                # Find and clear sessions
                pattern = f"imperal:session:{imperal_id}:*"
                session_keys = self.redis.keys(pattern) or []
                for k in session_keys:
                    self.redis.delete(k)
                    cleared_keys.append(str(k))

                # Clear telegram binds
                tg_pattern = "imperal:bind:telegram:*"
                tg_keys = self.redis.keys(tg_pattern) or []
                for k in tg_keys:
                    bound_id = self.redis.get(k)
                    if bound_id and (bound_id == imperal_id or bound_id == imperal_id.encode()):
                        self.redis.delete(k)
                        cleared_keys.append(str(k))
            except Exception as e:
                logger.error("Error during Redis deactivation cascade for %s: %s", imperal_id, e)

        if self.temporal is not None:
            workflow_id = f"personal-{imperal_id}"
            try:
                self.temporal.terminate_workflow(
                    workflow_id=workflow_id,
                    reason=f"I-DEACTIVATED-USER-GUARD cascade: {reason}"
                )
                workflow_terminated = True
            except Exception as e:
                logger.warning("Could not terminate Temporal workflow %s (might not exist): %s", workflow_id, e)

        return {
            "status": "deactivated",
            "imperal_id": imperal_id,
            "workflow_id": f"personal-{imperal_id}",
            "workflow_terminated": workflow_terminated,
            "cleared_keys_count": len(cleared_keys),
            "reason": reason,
        }
