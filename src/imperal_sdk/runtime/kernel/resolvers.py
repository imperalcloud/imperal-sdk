# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Kernel HTTP resolvers — identity, config, confirmation settings.

All resolve from Auth Gateway with Redis caching.
"""
from __future__ import annotations

import json as _json
import logging
import os

log = logging.getLogger(__name__)


def _get_redis():
    """Get shared Redis client."""
    try:
        from shared_redis import get_shared_redis
        return get_shared_redis()
    except ImportError:
        return None


def _gateway_config() -> tuple:
    """Return (gateway_url, service_token). Single source for all resolvers."""
    return (
        os.getenv("IMPERAL_GATEWAY_URL", "http://104.224.88.155:8085"),
        os.getenv("IMPERAL_SERVICE_TOKEN", ""),
    )


async def _resolve_user_identity(user_id: str, email: str = "") -> dict:
    """Resolve user_id to full profile from Auth Gateway. Cached in Redis 5min.
    Uses direct GET /v1/users/{id} — O(1) instead of fetching all users."""
    if not user_id or user_id == "0":
        return {"id": user_id, "email": "", "role": "system", "scopes": ["*"], "attributes": {}, "tenant_id": "default", "is_active": True}

    cache_key = f"imperal:identity:{user_id}"
    try:
        r = _get_redis()
        if r:
            cached = await r.get(cache_key)
            if cached:
                return _json.loads(cached)
    except Exception:
        pass

    gw_url, svc_token = _gateway_config()

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            # Direct lookup by imperal_id — O(1)
            resp = await client.get(
                f"{gw_url}/v1/users/{user_id}",
                headers={"X-Service-Token": svc_token},
            )
            if resp.status_code == 200:
                u = resp.json()
                profile = {
                    "id": str(u.get("imperal_id", u.get("id", user_id))),
                    "email": u.get("email", ""),
                    "role": u.get("role", "user"),
                    "scopes": u.get("scopes") or ["*"],
                    "attributes": u.get("attributes", {}),
                    "tenant_id": u.get("tenant_id", "default"),
                    "is_active": u.get("is_active", True),
                }
                try:
                    r = _get_redis()
                    if r:
                        await r.setex(cache_key, 300, _json.dumps(profile))
                except Exception:
                    pass
                return profile

            # Fallback: search by email if direct lookup failed
            if email:
                resp = await client.get(
                    f"{gw_url}/v1/users?search={email}&limit=1",
                    headers={"X-Service-Token": svc_token},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", data) if isinstance(data, dict) else data
                    if isinstance(items, list) and items:
                        u = items[0]
                        profile = {
                            "id": str(u.get("imperal_id", u.get("id", user_id))),
                            "email": u.get("email", ""),
                            "role": u.get("role", "user"),
                            "scopes": u.get("scopes") or ["*"],
                            "attributes": u.get("attributes", {}),
                            "tenant_id": u.get("tenant_id", "default"),
                            "is_active": u.get("is_active", True),
                        }
                        try:
                            r = _get_redis()
                            if r:
                                await r.setex(cache_key, 300, _json.dumps(profile))
                        except Exception:
                            pass
                        return profile

    except Exception as e:
        log.warning(f"Identity resolution failed for user {user_id}: {e}")

    return {"id": user_id, "email": "", "role": "user", "scopes": ["*"], "attributes": {}, "tenant_id": "default", "is_active": True}


async def _resolve_config(tenant_id: str, app_id: str, role: str, user_id: str) -> dict:
    """Resolve config for user+app+tenant from Auth Gateway. Redis cached 300s."""
    cache_key = f"imperal:config:resolved:{tenant_id}:{app_id}:{role}:{user_id}"
    try:
        r = _get_redis()
        if r:
            cached = await r.get(cache_key)
            if cached:
                return _json.loads(cached)
    except Exception:
        pass

    try:
        import httpx
        gw_url, svc_token = _gateway_config()
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{gw_url}/v1/internal/config/resolve",
                params={"tenant_id": tenant_id, "app_id": app_id, "role": role, "user_id": user_id},
                headers={"X-Service-Token": svc_token},
            )
            if resp.status_code == 200:
                resolved = resp.json()
                try:
                    r = _get_redis()
                    if r:
                        await r.setex(cache_key, 300, _json.dumps(resolved))
                except Exception:
                    pass
                return resolved
    except Exception as e:
        log.warning(f"Config resolve error: {e}")
    return {}


async def _resolve_confirmation_settings(user_id: str, tenant_id: str) -> dict:
    """Fetch user confirmation + KAV settings from Auth Gateway.
    Returns defaults on failure (confirmation off, KAV retries 2)."""
    defaults = {
        "confirmation_enabled": False,
        "confirmation_actions": [],
        "confirmation_overrides": {},
        "kav_max_retries": 2,
        "confirmation_ttl": 300,
    }
    try:
        import httpx
        gw_url, svc_token = _gateway_config()
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{gw_url}/v1/internal/users/{user_id}/settings",
                params={"tenant_id": tenant_id},
                headers={"X-Service-Token": svc_token},
            )
            if resp.status_code == 200:
                data = resp.json()
                # Settings may be nested under "settings" key
                settings = data.get("settings", data) if isinstance(data, dict) else data
                return {
                    "confirmation_enabled": settings.get("confirmation_enabled", False),
                    "confirmation_actions": settings.get("confirmation_actions", {}),
                    "confirmation_overrides": settings.get("confirmation_overrides", {}),
                    "kav_max_retries": settings.get("kav_max_retries", 2),
                    "confirmation_ttl": settings.get("confirmation_ttl", 300),
                }
    except Exception as e:
        log.debug(f"Confirmation settings fetch failed for user {user_id}: {e}")
    return defaults
