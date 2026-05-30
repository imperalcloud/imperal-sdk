"""The live SDK-vs-kernel-contract mirror. Green proves the corrected SDK
agrees with the kernel contract on all three static layers. The kernel-CI
guard (Plan 1b) runs the same checks against a *real* kernel-contract.json."""
import json
import pathlib

import httpx
import respx

from imperal_sdk.devtools.generate_sdk_claims import generate_claims
from imperal_sdk.devtools.contract_checks import (
    check_constant_depth, check_decorator_roles, check_wire_payload,
)

CONTRACT = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "contract"
     / "kernel-contract.sample.json").read_text())
CLAIMS = generate_claims()
ROUTE = "POST /v1/billing/internal/usage/track"


def test_semantic_depth_matches():
    assert check_constant_depth(CLAIMS, CONTRACT) == []


def test_decorator_roles_match():
    assert check_decorator_roles(CLAIMS["decorator_roles"], CONTRACT) == []


@respx.mock
async def test_track_usage_payload_matches_request_model():
    captured: dict = {}

    def _capture(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": "tracked"})

    respx.post("http://gw.test/v1/billing/internal/usage/track").mock(side_effect=_capture)

    from imperal_sdk.billing.client import BillingClient
    client = BillingClient(gateway_url="http://gw.test", auth_token="t",
                           service_token="svc", user_id="u1")
    ok = await client.track_usage("llm", 100)
    assert ok is True

    findings = check_wire_payload(ROUTE, set(captured), CONTRACT)
    assert findings == [], f"track_usage payload drifts from request model: {findings}"


@respx.mock
async def test_track_usage_without_uid_payload_is_flagged():
    """Coverage for the no-user-context path: track_usage with a service token
    but no uid sends only {meter, quantity}, omitting the contract-required
    user_id/tenant_id. The guard must flag this — usage must be attributed to
    a user. (Documents a minor latent edge in track_usage's no-uid payload.)"""
    captured: dict = {}

    def _capture(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": "tracked"})

    respx.post("http://gw.test/v1/billing/internal/usage/track").mock(side_effect=_capture)

    from imperal_sdk.billing.client import BillingClient
    client = BillingClient(gateway_url="http://gw.test", auth_token="t", service_token="svc")  # no user_id
    await client.track_usage("llm", 100)

    findings = check_wire_payload(ROUTE, set(captured), CONTRACT)
    assert any("user_id" in f.detail or "tenant_id" in f.detail for f in findings), \
        f"guard should flag the no-uid payload missing required fields; got {findings}"
