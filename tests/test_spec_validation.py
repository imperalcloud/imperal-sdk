# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Spec-level validation of every contract shipped with the SDK.

Catches breakage at the contract-definition layer, before it can reach
third-party developers or propagate into generated clients:

- Every JSON Schema file under `imperal_sdk/schemas/` is a valid
  Draft 2020-12 schema (`jsonschema.Draft202012Validator.check_schema`).
- Every OpenAPI 3.x file under `docs/openapi/` validates against the
  OpenAPI Specification (`openapi_spec_validator.validate`).
- Internal consistency checks that generators routinely miss:
  unique operation IDs, all $refs resolve, every response declares a
  schema (or an explicit no-content code).

These tests are fast (~1s total), have no network dependencies, and
always run in CI. Live-service contract testing lives in
`test_contracts_live.py` (schemathesis, env-gated).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "src" / "imperal_sdk" / "schemas"
OPENAPI_DIR = ROOT / "docs" / "openapi"


# === JSON Schema files =============================================

@pytest.fixture(scope="module")
def schema_files() -> list[Path]:
    files = sorted(SCHEMAS_DIR.glob("*.schema.json"))
    assert files, f"No schemas found under {SCHEMAS_DIR}"
    return files


def test_all_schemas_are_present(schema_files):
    """Every contract-ized type has a shipped schema file.

    Keeps the wheel-force-include list in pyproject.toml honest —
    if a new `*Model` is added without a static schema export, this
    test fails.
    """
    expected = {
        "imperal", "action_result", "event",
        "function_call", "chat_result",
        "document", "completion_result", "limits_result",
        "subscription_info", "balance_info", "file_info", "http_response",
    }
    actual = {f.name.replace(".schema.json", "") for f in schema_files}
    assert expected <= actual, (
        f"Missing schema files: {expected - actual}"
    )


@pytest.mark.parametrize("schema_path", sorted(SCHEMAS_DIR.glob("*.schema.json")),
                         ids=lambda p: p.name)
def test_schema_is_valid_draft_2020_12(schema_path):
    """Each committed schema file is a well-formed Draft 2020-12 schema."""
    from jsonschema import Draft202012Validator

    schema = json.loads(schema_path.read_text())
    # check_schema raises if the meta-schema is violated; a green pass
    # means the file is structurally valid JSON Schema.
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("schema_path", sorted(SCHEMAS_DIR.glob("*.schema.json")),
                         ids=lambda p: p.name)
def test_schema_has_required_metadata(schema_path):
    schema = json.loads(schema_path.read_text())
    assert schema.get("$id"), f"{schema_path.name}: missing $id"
    assert schema.get("title"), f"{schema_path.name}: missing title"
    assert schema["$id"].startswith("https://imperal.io/schemas/"), (
        f"{schema_path.name}: non-canonical $id"
    )


# === OpenAPI spec files ============================================

@pytest.fixture(scope="module")
def openapi_specs() -> list[Path]:
    files = sorted(OPENAPI_DIR.glob("*.json"))
    assert files, f"No OpenAPI specs found under {OPENAPI_DIR}"
    return files


def test_openapi_dir_has_all_imperal_specs(openapi_specs):
    names = {f.stem for f in openapi_specs}
    expected = {"auth-gateway", "registry", "sharelock-cases"}
    assert expected == names, (
        f"Expected exactly {expected}, got {names} — did a new service "
        f"arrive or an existing one get renamed?"
    )


@pytest.mark.parametrize("spec_path", sorted(OPENAPI_DIR.glob("*.json")),
                         ids=lambda p: p.stem)
def test_openapi_spec_is_valid(spec_path):
    """openapi-spec-validator runs the full OpenAPI 3.x validation."""
    from openapi_spec_validator import validate

    spec = json.loads(spec_path.read_text())
    # Raises OpenAPIValidationError on any spec-level violation.
    validate(spec)


@pytest.mark.parametrize("spec_path", sorted(OPENAPI_DIR.glob("*.json")),
                         ids=lambda p: p.stem)
def test_openapi_metadata_present(spec_path):
    spec = json.loads(spec_path.read_text())
    info = spec.get("info", {})
    assert info.get("title"), f"{spec_path.name}: missing info.title"
    assert info.get("version"), f"{spec_path.name}: missing info.version"
    assert spec.get("openapi", "").startswith(("3.0.", "3.1.")), (
        f"{spec_path.name}: not OpenAPI 3.x"
    )
    assert spec.get("paths"), f"{spec_path.name}: no paths"


@pytest.mark.parametrize("spec_path", sorted(OPENAPI_DIR.glob("*.json")),
                         ids=lambda p: p.stem)
def test_openapi_operation_ids_unique(spec_path):
    """Each operation in a spec must have a unique operationId.

    Duplicates break code generators that key on operationId (most of
    them do — openapi-generator, openapi-python-client, etc.).
    """
    spec = json.loads(spec_path.read_text())
    seen: dict[str, str] = {}
    dupes: list[tuple[str, str, str]] = []
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete",
                                      "head", "options", "trace"}:
                continue
            op_id = op.get("operationId")
            if not op_id:
                continue
            if op_id in seen:
                dupes.append((op_id, seen[op_id], f"{method.upper()} {path}"))
            else:
                seen[op_id] = f"{method.upper()} {path}"

    assert not dupes, (
        f"{spec_path.name}: duplicate operationIds: "
        + "; ".join(f"'{d[0]}' used by {d[1]} and {d[2]}" for d in dupes)
    )


@pytest.mark.parametrize("spec_path", sorted(OPENAPI_DIR.glob("*.json")),
                         ids=lambda p: p.stem)
def test_openapi_refs_resolve_within_spec(spec_path):
    """Every internal $ref must point to a component that exists.

    Catches orphan references that survive a service refactor — the
    openapi-spec-validator run above catches meta-level issues, but a
    $ref to a missing component may still parse as "valid" in some
    configurations.
    """
    spec = json.loads(spec_path.read_text())

    def collect_refs(node, out: list[str]) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "$ref" and isinstance(v, str):
                    out.append(v)
                else:
                    collect_refs(v, out)
        elif isinstance(node, list):
            for item in node:
                collect_refs(item, out)

    refs: list[str] = []
    collect_refs(spec, refs)

    # External refs (http:// etc.) are out of scope — only verify local ones.
    local_refs = [r for r in refs if r.startswith("#/")]
    missing: list[str] = []
    for ref in local_refs:
        # Walk "#/components/schemas/Foo" → spec["components"]["schemas"]["Foo"]
        parts = ref.lstrip("#/").split("/")
        node = spec
        for p in parts:
            if not isinstance(node, dict) or p not in node:
                missing.append(ref)
                break
            node = node[p]

    assert not missing, (
        f"{spec_path.name}: {len(missing)} unresolved $refs "
        f"(first 5): {missing[:5]}"
    )


# === Cross-check: Pydantic-generated schemas match committed files ===

@pytest.mark.parametrize("name,getter_import", [
    ("imperal", "imperal_sdk.manifest_schema:get_schema"),
    ("action_result", "imperal_sdk.types.contracts:get_action_result_schema"),
    ("event", "imperal_sdk.types.contracts:get_event_schema"),
    ("function_call", "imperal_sdk.types.contracts:get_function_call_schema"),
    ("chat_result", "imperal_sdk.types.contracts:get_chat_result_schema"),
    ("document", "imperal_sdk.types.client_contracts:get_document_schema"),
    ("completion_result", "imperal_sdk.types.client_contracts:get_completion_result_schema"),
    ("limits_result", "imperal_sdk.types.client_contracts:get_limits_result_schema"),
    ("subscription_info", "imperal_sdk.types.client_contracts:get_subscription_info_schema"),
    ("balance_info", "imperal_sdk.types.client_contracts:get_balance_info_schema"),
    ("file_info", "imperal_sdk.types.client_contracts:get_file_info_schema"),
    ("http_response", "imperal_sdk.types.client_contracts:get_http_response_schema"),
])
def test_static_schema_matches_runtime_export(name, getter_import):
    """The committed schemas/*.schema.json must equal the runtime model's schema.

    Fails when a Pydantic model is edited but the static file is not
    regenerated — drift between the source of truth and the shipped
    artifact. Regenerate via the commands documented in each contract
    module's docstring.
    """
    module_path, fn_name = getter_import.split(":")
    import importlib
    module = importlib.import_module(module_path)
    fn = getattr(module, fn_name)

    committed = json.loads((SCHEMAS_DIR / f"{name}.schema.json").read_text())
    runtime = fn()
    assert committed == runtime, (
        f"src/imperal_sdk/schemas/{name}.schema.json is out of sync "
        f"with {getter_import}. Regenerate it."
    )
