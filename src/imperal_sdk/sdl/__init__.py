"""SDL — Structured Data Layer. Typed semantic vocabulary for entity data.

Public surface:
    Entity, Ref, EntityList   — canonical entity types
    field                     — declare a typed custom-role field
    roles_of                  — field->role introspection
    is_valid_role, validate_custom_role, namespace_of, RoleError,
    RESERVED_NAMESPACES, CORE_ROLES   — role registry
"""
from imperal_sdk.sdl.entity import Entity, Ref, EntityList, roles_of
from imperal_sdk.sdl.field import field, ROLE_KEY
from imperal_sdk.sdl.roles import (
    is_valid_role, namespace_of, validate_custom_role,
    RoleError, RESERVED_NAMESPACES, CORE_ROLES,
)

__all__ = [
    "Entity", "Ref", "EntityList", "roles_of",
    "field", "ROLE_KEY",
    "is_valid_role", "namespace_of", "validate_custom_role",
    "RoleError", "RESERVED_NAMESPACES", "CORE_ROLES",
]
