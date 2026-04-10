"""Action Writer — records completed actions to Auth Gateway action_ledger."""
import logging
import os
import uuid

import httpx

log = logging.getLogger(__name__)


def generate_trace_id() -> str:
    """Generate a unique trace ID for action tracking."""
    return uuid.uuid4().hex[:16]


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
    llm_steps: list | None = None,
    llm_total_calls: int = 0,
    llm_total_tokens: int = 0,
) -> bool:
    """Write action record to Auth Gateway. Returns True on success."""
    if not gateway_url or not service_token:
        log.warning("write_action: missing gateway_url or service_token")
        return False

    _worker_id = worker_id or os.getenv("WORKER_INSTANCE", "")

    payload = {
        "trace_id": trace_id,
        "chain_id": chain_id,
        "parent_task_id": parent_task_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "app_id": app_id,
        "tool_name": tool_name,
        "action_type": action_type,
        "intent_type": intent_type,
        "status": status,
        "message_preview": (message_preview or "")[:200],
        "result_preview": (result_preview or "")[:200],
        "error": error,
        "duration_ms": duration_ms,
        "tokens_used": tokens_used,
        "heartbeat_count": heartbeat_count,
        "action_price": action_price,
        "extension_price": extension_price,
        "platform_fee": 0.0,
        "worker_id": _worker_id,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_steps": llm_steps,
        "llm_total_calls": llm_total_calls,
        "llm_total_tokens": llm_total_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{gateway_url}/v1/actions",
                json=payload,
                headers={"X-Service-Token": service_token, "Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return True
            log.warning(f"write_action failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        log.warning(f"write_action error: {e}")
        return False
