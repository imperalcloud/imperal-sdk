import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def publish_kernel_event(
    redis_client,
    tenant_id: str,
    event_type: str,
    data: dict,
    user_id: str,
    app_id: str,
    function_name: str,
    action_type: str,
    timestamp: str,
):
    """Publish a kernel event to Redis pub/sub for automations and SSE.
    
    Non-blocking: errors are logged, never raised.
    """
    event = {
        "event_type": event_type,
        "data": data,
        "context": {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "app_id": app_id,
            "function_name": function_name,
            "action_type": action_type,
            "timestamp": timestamp,
        }
    }
    channel = f"imperal:events:{tenant_id}"
    try:
        await redis_client.publish(channel, json.dumps(event, default=str))
        logger.info(f"Event published: {event_type} by {user_id} via {function_name}")
    except Exception as e:
        logger.error(f"Event publish failed: {event_type} — {e}")
