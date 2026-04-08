"""Async non-blocking action writer — records actions to Auth Gateway.

Fire-and-forget: never blocks, never raises. Failures are logged only.
"""
import logging
import os
import uuid

log = logging.getLogger(__name__)


def generate_trace_id() -> str:
    """Generate a unique trace ID for action tracking."""
    return f"act_{uuid.uuid4().hex[:8]}"


async def write_action(
    gateway_url: str,
    service_token: str,
    trace_id: str,
    user_id: str,
    tenant_id: str,
    app_id: str,
    tool_name: str,
    action_type: str,
    intent_type: str,
    status: str,
    message_preview: str = "",
    result_preview: str = "",
    error: str | None = None,
    duration_ms: int = 0,
    tokens_used: int = 0,
    heartbeat_count: int = 0,
    action_price: float = 0.0,
    extension_price: float = 0.0,
    chain_id: str | None = None,
    parent_task_id: str | None = None,
    worker_id: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    user_scopes: list | None = None,
    checked_scopes: list | None = None,
) -> bool:
    """Write an action record to Auth Gateway. Non-blocking, never raises.

    Pricing rules:
    - status != "completed" → action_price=0, extension_price=0, platform_fee=0
    - status == "completed" → platform_fee = action_price * 0.30
    """
    try:
        import httpx

        # Pricing logic
        if status != "completed":
            action_price = 0.0
            extension_price = 0.0
            platform_fee = 0.0
        else:
            platform_fee = round(action_price * 0.30, 6)

        # Truncate previews
        message_preview = (message_preview or "")[:200]
        result_preview = (result_preview or "")[:200]

        payload = {
            "trace_id": trace_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "app_id": app_id,
            "tool_name": tool_name,
            "action_type": action_type,
            "intent_type": intent_type,
            "status": status,
            "message_preview": message_preview,
            "result_preview": result_preview,
            "error": error,
            "duration_ms": duration_ms,
            "tokens_used": tokens_used,
            "heartbeat_count": heartbeat_count,
            "action_price": action_price,
            "extension_price": extension_price,
            "platform_fee": platform_fee,
            "chain_id": chain_id,
            "parent_task_id": parent_task_id,
            "worker_id": worker_id or os.getenv("HOSTNAME", "unknown"),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "user_scopes": user_scopes,
            "checked_scopes": checked_scopes,
        }

        log.info(f"Writing action: trace={trace_id} app={app_id} status={status} → {gateway_url}/v1/actions")
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{gateway_url}/v1/actions",
                json=payload,
                headers={"X-Service-Token": service_token},
            )
            if resp.status_code in (200, 201):
                log.debug(f"Action written: trace={trace_id} app={app_id}/{tool_name} status={status}")
                return True
            else:
                log.warning(f"Action write failed: {resp.status_code} trace={trace_id}")
                return False

    except Exception as e:
        log.warning(f"Action write error: {e} trace={trace_id}")
        return False
