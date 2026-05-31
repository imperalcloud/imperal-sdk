"""sdl.field — declare a typed field carrying an explicit SDL semantic role.

The role is stamped into the Pydantic field's ``json_schema_extra`` under the
``x-sdl-role`` key, so the kernel and validators can read field→role mapping from
``model_json_schema()`` / ``model_fields``. Custom roles are validated eagerly
(at class definition time) and must use a non-reserved namespace.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from imperal_sdk.sdl.roles import validate_custom_role

ROLE_KEY = "x-sdl-role"


def field(*, role: str, describe: str | None = None, default: Any = None, **kwargs: Any):
    """Pydantic field carrying an SDL semantic ``role``.

    Args:
        role: dotted custom role in a non-reserved namespace (validated eagerly).
        describe: optional human description (stored as the field description).
        default: field default. Defaults to ``None`` (optional). Pass
            ``default=...`` (Ellipsis) to make the field required.
        **kwargs: forwarded to ``pydantic.Field``.
    """
    validate_custom_role(role)
    json_schema_extra: dict[str, Any] = dict(kwargs.pop("json_schema_extra", None) or {})
    json_schema_extra[ROLE_KEY] = role
    if describe is not None:
        json_schema_extra.setdefault("description", describe)
    return Field(default, json_schema_extra=json_schema_extra, **kwargs)
