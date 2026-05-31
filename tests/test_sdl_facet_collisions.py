# tests/test_sdl_facet_collisions.py
"""SDL Phase 2 — no two facets share a field NAME with DIFFERENT roles (co-mix safety)."""
from __future__ import annotations

import imperal_sdk.sdl.facets as facets
from imperal_sdk.sdl.entity import roles_of


def test_no_cross_facet_field_name_role_collisions():
    seen: dict[str, tuple[str, str]] = {}   # field_name -> (role, facet)
    conflicts = []
    for facet_name in facets.__all__:
        model = getattr(facets, facet_name)
        for field_name, role in roles_of(model).items():
            if field_name in seen and seen[field_name][0] != role:
                prev_role, prev_facet = seen[field_name]
                conflicts.append(f"{field_name}: {prev_facet}={prev_role} vs {facet_name}={role}")
            else:
                seen.setdefault(field_name, (role, facet_name))
    assert not conflicts, "field-name/role collisions:\n" + "\n".join(conflicts)
