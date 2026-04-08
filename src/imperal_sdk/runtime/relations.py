"""App Relations — context firewall between extensions.

Controls which extensions can share data with each other.
Stored in Unified Config Store as tenant-level config.
"""
import json
import logging
import os

import httpx

log = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("IMPERAL_GATEWAY_URL", "http://104.224.88.155:8085")
SERVICE_TOKEN = os.getenv("IMPERAL_SERVICE_TOKEN", "")

DEFAULT_RELATIONS = {"default_policy": "allow", "rules": []}


async def load_app_relations(tenant_id: str = "default") -> dict:
    """Load app relations config from Unified Config Store."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{GATEWAY_URL}/v1/internal/config/resolve",
                params={"tenant_id": tenant_id, "key": "app_relations", "scope": "tenant"},
                headers={"X-Service-Token": SERVICE_TOKEN},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("value", DEFAULT_RELATIONS) if isinstance(data, dict) else DEFAULT_RELATIONS
    except Exception as e:
        log.debug(f"Failed to load app relations: {e}")
    return DEFAULT_RELATIONS


def relations_allow(relations: dict, source_app: str, target_app: str) -> bool:
    """Check if source extension can pass data to target extension.
    
    Admin and __system__ always allowed.
    Default policy 'allow' means all cross-extension sharing is permitted unless explicitly denied.
    """
    if source_app in ("admin", "__system__") or target_app in ("admin", "__system__"):
        return True
    if source_app == target_app:
        return True
    
    policy = relations.get("default_policy", "allow")
    rules = relations.get("rules", [])
    
    for rule in rules:
        if rule.get("source") == source_app and rule.get("target") == target_app:
            return rule.get("allow", policy == "allow")
    
    return policy == "allow"
