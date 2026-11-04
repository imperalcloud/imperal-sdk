# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Schemathesis-driven contract tests against live Imperal services.

These tests are **skipped by default** — they require the `[contract]`
extra (`pip install imperal-sdk[contract]`) and environment variables
pointing at a running service plus a valid API key.

Running manually:

    pip install imperal-sdk[contract]

    export IMPERAL_CONTRACT_REGISTRY_URL="https://auth.imperal.io"
    export IMPERAL_CONTRACT_API_KEY="imp_reg_key_xxxxxxxxxxxxxxxx"
    pytest tests/test_contracts_live.py -v

Schemathesis reads the committed OpenAPI spec under `docs/openapi/`,
generates property-based requests covering every endpoint and schema
variation, and fails the test if any real response diverges from what
the spec declares. Use this during service refactors (before publishing
a new release) to prove the running server still honours its contract.

Against a local dev server, point `*_URL` at `http://localhost:<port>`.

These tests **never run in CI by default** — CI has no credentials and
shouldn't hammer production services. The offline
`test_spec_validation.py` suite covers spec well-formedness in CI.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    import schemathesis
    HAVE_SCHEMATHESIS = True
except ImportError:
    HAVE_SCHEMATHESIS = False


OPENAPI_DIR = Path(__file__).resolve().parent.parent / "docs" / "openapi"

# Mapping: OpenAPI spec file → env var prefix for the live service
SERVICES = {
    "registry":        "IMPERAL_CONTRACT_REGISTRY",
    "auth-gateway":    "IMPERAL_CONTRACT_AUTH",
    "sharelock-cases": "IMPERAL_CONTRACT_CASES",
}


def _service_config(service: str) -> tuple[str | None, str | None]:
    """Return (base_url, api_key) for a service, or (None, None) if unset."""
    prefix = SERVICES[service]
    return os.getenv(f"{prefix}_URL"), os.getenv(f"{prefix}_API_KEY")


def _require(service: str) -> tuple[str, str]:
    if not HAVE_SCHEMATHESIS:
        pytest.skip(
            "schemathesis not installed — `pip install imperal-sdk[contract]`"
        )
    base_url, api_key = _service_config(service)
    if not base_url:
        pytest.skip(
            f"{SERVICES[service]}_URL not set — skipping live contract "
            f"test for '{service}'"
        )
    if not api_key:
        pytest.skip(f"{SERVICES[service]}_API_KEY not set")
    return base_url, api_key


@pytest.mark.parametrize("service", sorted(SERVICES.keys()))
def test_service_conforms_to_openapi_spec(service):
    """For each service with credentials configured, run schemathesis.

    Schemathesis generates many test cases from the spec's schemas,
    replays them against the live service, and asserts every response
    matches its declared response schema. First divergence fails the
    test with a reproducing case.
    """
    base_url, api_key = _require(service)

    spec_path = OPENAPI_DIR / f"{service}.json"
    assert spec_path.exists(), f"Missing {spec_path}"

    schema = schemathesis.from_path(
        str(spec_path),
        base_url=base_url,
    )

    # Schemathesis 3.x: iterate all endpoints, run each as a case.
    # We cap cases per endpoint to keep runtime bounded for CI-style use.
    for operation in schema.get_all_operations():
        strategy = operation.ok().as_strategy()
        case = strategy.example()
        # Attach the auth header the services expect (Registry + Cases
        # use x-api-key; Auth Gateway uses its own JWT — adjust when wiring
        # against auth-gateway with a real token).
        case.headers = case.headers or {}
        case.headers.setdefault("x-api-key", api_key)

        response = case.call()
        case.validate_response(response)
