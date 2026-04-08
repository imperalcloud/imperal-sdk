"""Cascade Map — L8 dependency graph for extension cascading effects.

Maps which extensions are affected when another changes data.
Used by skeleton workflow to know which sections to refresh.
"""
import logging

log = logging.getLogger(__name__)

_cascade_map: dict = {}


async def build_cascade_map(extensions_config: list) -> dict:
    """Build cascade dependency map from extension configs.
    
    Returns: {app_id: [affected_app_ids]}
    """
    global _cascade_map
    cascade = {}
    for ext in extensions_config:
        app_id = ext.get("app_id", "")
        deps = ext.get("cascade_deps", [])
        if app_id and deps:
            cascade[app_id] = deps
    _cascade_map = cascade
    log.info(f"Cascade map built: {len(cascade)} extensions with dependencies")
    return cascade


async def get_cascade_map() -> dict:
    """Get the current cascade map."""
    return _cascade_map


async def get_cascade_effects(app_id: str) -> list:
    """Get list of extensions affected by changes in app_id."""
    effects = []
    for source, targets in _cascade_map.items():
        if app_id in targets:
            effects.append(source)
    # Also direct targets
    effects.extend(_cascade_map.get(app_id, []))
    return list(set(effects))
