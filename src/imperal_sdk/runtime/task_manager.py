"""Task Manager — Redis-based task lifecycle management.

Every action is a Task. Threshold determines visibility.
All functions take redis client as first argument (injected by executor).

Redis keys:
  imperal:task:{task_id}         — task record (JSON, TTL 24h)
  imperal:tasks:user:{user_id}   — active task IDs (SET)
"""
import json
import logging
import time
import uuid

log = logging.getLogger(__name__)

TASK_TTL = 86400  # 24 hours
STALE_THRESHOLD_S = 600  # 10 minutes


def generate_task_id() -> str:
    return uuid.uuid4().hex[:16]


async def create_task(
    redis, task_id: str, user_id: str, tenant_id: str, app_id: str,
    tool_name: str, message_preview: str = "", visible: bool = False,
    threshold_ms: int = 5000
) -> dict:
    record = {
        "task_id": task_id, "user_id": user_id, "tenant_id": tenant_id,
        "app_id": app_id, "tool_name": tool_name,
        "message_preview": (message_preview or "")[:200],
        "status": "running", "visible": visible,
        "progress": 0, "progress_message": "",
        "threshold_ms": threshold_ms,
        "created_at": time.time(), "heartbeat_count": 0,
    }
    await redis.set(f"imperal:task:{task_id}", json.dumps(record), ex=TASK_TTL)
    await redis.sadd(f"imperal:tasks:user:{user_id}", task_id)
    return record


async def promote_task(redis, task_id: str) -> None:
    raw = await redis.get(f"imperal:task:{task_id}")
    if raw:
        record = json.loads(raw)
        record["status"] = "promoted"
        record["visible"] = True
        record["promoted_at"] = time.time()
        await redis.set(f"imperal:task:{task_id}", json.dumps(record), ex=TASK_TTL)


async def update_progress(redis, task_id: str, percent: int, message: str = "") -> bool:
    raw = await redis.get(f"imperal:task:{task_id}")
    if not raw:
        return False
    record = json.loads(raw)
    record["progress"] = percent
    record["progress_message"] = message
    record["heartbeat_count"] = record.get("heartbeat_count", 0) + 1
    await redis.set(f"imperal:task:{task_id}", json.dumps(record), ex=TASK_TTL)
    return record.get("status") != "cancelled"


async def complete_task(redis, task_id: str, user_id: str, status: str = "completed", result_preview: str = "") -> None:
    raw = await redis.get(f"imperal:task:{task_id}")
    if raw:
        record = json.loads(raw)
        record["status"] = status
        record["progress"] = 100
        record["completed_at"] = time.time()
        record["duration_ms"] = int((time.time() - record.get("created_at", time.time())) * 1000)
        if result_preview:
            record["result_preview"] = result_preview[:200]
        await redis.set(f"imperal:task:{task_id}", json.dumps(record), ex=TASK_TTL)
    await redis.srem(f"imperal:tasks:user:{user_id}", task_id)


async def get_task(redis, task_id: str) -> dict | None:
    raw = await redis.get(f"imperal:task:{task_id}")
    return json.loads(raw) if raw else None


def _is_stale(record: dict) -> bool:
    created = record.get("created_at", 0)
    status = record.get("status", "")
    if status in ("promoted", "running") and time.time() - created > STALE_THRESHOLD_S:
        return True
    return False


async def _auto_fail_stale(redis, user_id: str, task_ids: set) -> set:
    clean = set()
    for tid in task_ids:
        tid_str = tid if isinstance(tid, str) else tid.decode("utf-8")
        raw = await redis.get(f"imperal:task:{tid_str}")
        if not raw:
            await redis.srem(f"imperal:tasks:user:{user_id}", tid_str)
            continue
        record = json.loads(raw)
        if _is_stale(record):
            record["status"] = "failed"
            record["error"] = "Task stale — auto-failed after 10 min"
            record["completed_at"] = time.time()
            await redis.set(f"imperal:task:{tid_str}", json.dumps(record), ex=TASK_TTL)
            await redis.srem(f"imperal:tasks:user:{user_id}", tid_str)
            log.warning(f"Auto-failed stale task {tid_str} for user {user_id}")
        else:
            clean.add(tid_str)
    return clean


async def get_active_tasks(redis, user_id: str) -> list:
    task_ids = await redis.smembers(f"imperal:tasks:user:{user_id}")
    if not task_ids:
        return []
    task_ids = await _auto_fail_stale(redis, user_id, task_ids)
    tasks = []
    for tid in task_ids:
        raw = await redis.get(f"imperal:task:{tid}")
        if raw:
            record = json.loads(raw)
            if record.get("visible"):
                tasks.append(record)
    return sorted(tasks, key=lambda t: t.get("created_at", 0), reverse=True)


async def count_active_tasks(redis, user_id: str) -> int:
    task_ids = await redis.smembers(f"imperal:tasks:user:{user_id}")
    if not task_ids:
        return 0
    clean = await _auto_fail_stale(redis, user_id, task_ids)
    return len(clean)


async def is_cancelled(redis, task_id: str) -> bool:
    raw = await redis.get(f"imperal:task:{task_id}")
    if not raw:
        return True
    record = json.loads(raw)
    return record.get("status") == "cancelled"
