# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from imperal_sdk.billing.client import LimitsResult, SubscriptionInfo


def test_limits_result_not_exceeded():
    limits = LimitsResult(
        plan="free",
        usage={"ai_tokens": 5000},
        limits={"ai_tokens": 10000},
        exceeded=[],
    )
    assert limits.any_exceeded is False
    assert limits.is_exceeded("ai_tokens") is False


def test_limits_result_exceeded():
    limits = LimitsResult(
        plan="free",
        usage={"ai_tokens": 15000},
        limits={"ai_tokens": 10000},
        exceeded=["ai_tokens"],
    )
    assert limits.any_exceeded is True
    assert limits.is_exceeded("ai_tokens") is True
    assert limits.is_exceeded("tool_calls") is False


def test_subscription_info():
    sub = SubscriptionInfo(plan="pro", status="active", started_at="2026-01-01T00:00:00")
    assert sub.plan == "pro"
    assert sub.status == "active"
    assert sub.expires_at is None


import json
import httpx
import respx
from imperal_sdk.billing.client import BillingClient

_GW = "http://gw.test"


@respx.mock
async def test_list_payment_methods_internal_path():
    respx.get(f"{_GW}/v1/billing/internal/payment-methods/imp_u_x").mock(
        return_value=httpx.Response(200, json=[{"id": "pm_1", "type": "card", "brand": "visa",
            "last4": "4242", "exp_month": 12, "exp_year": 2030, "is_default": True}]))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    pms = await c.list_payment_methods()
    assert pms[0].last4 == "4242" and pms[0].is_default is True


@respx.mock
async def test_change_plan_posts_plan_and_period_with_acting_user():
    route = respx.post(f"{_GW}/v1/billing/change-plan").mock(
        return_value=httpx.Response(200, json={"action": "upgrade", "succeeded": True, "plan": "business"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    res = await c.change_plan("plan_bus", "monthly")
    assert res.action == "upgrade" and res.succeeded is True
    req = route.calls.last.request
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"
    assert json.loads(req.content) == {"plan_id": "plan_bus", "period": "monthly"}


@respx.mock
async def test_topup_returns_client_secret():
    respx.post(f"{_GW}/v1/billing/topup").mock(return_value=httpx.Response(200,
        json={"client_secret": "cs_1", "payment_intent_id": "pi_1", "publishable_key": "pk_1"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    r = await c.topup(tokens=20000, price_cents=2000)
    assert r.client_secret == "cs_1" and r.payment_intent_id == "pi_1"
