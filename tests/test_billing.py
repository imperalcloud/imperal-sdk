# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
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
    route = respx.post(f"{_GW}/v1/billing/topup").mock(return_value=httpx.Response(200,
        json={"client_secret": "cs_1", "payment_intent_id": "pi_1", "publishable_key": "pk_1"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    r = await c.topup(tokens=20000, price_cents=2000, off_session=False)
    assert r.client_secret == "cs_1" and r.payment_intent_id == "pi_1"
    # Element path defaults: succeeded/requires_action absent → False
    assert r.succeeded is False and r.requires_action is False
    body = json.loads(route.calls.last.request.content)
    assert body == {"tokens": 20000, "price_cents": 2000,
                    "save_payment_method": True, "off_session": False}


@respx.mock
async def test_topup_off_session_default_sends_flag_and_parses_succeeded():
    route = respx.post(f"{_GW}/v1/billing/topup").mock(return_value=httpx.Response(200,
        json={"payment_intent_id": "pi_2", "succeeded": True, "requires_action": False}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    r = await c.topup(tokens=20000, price_cents=2000)
    assert r.payment_intent_id == "pi_2"
    assert r.succeeded is True and r.requires_action is False
    assert r.client_secret == ""
    # off_session defaults to True and is included in the POST body
    assert json.loads(route.calls.last.request.content)["off_session"] is True


@respx.mock
async def test_topup_off_session_requires_action():
    respx.post(f"{_GW}/v1/billing/topup").mock(return_value=httpx.Response(200,
        json={"payment_intent_id": "pi_3", "client_secret": "cs_3",
              "succeeded": False, "requires_action": True}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    r = await c.topup(tokens=20000, price_cents=2000)
    assert r.requires_action is True and r.succeeded is False
    assert r.client_secret == "cs_3"


@respx.mock
async def test_create_billing_portal_session_returns_url():
    route = respx.post(f"{_GW}/v1/billing/portal").mock(return_value=httpx.Response(200,
        json={"url": "https://billing.stripe.com/p/session_x"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    url = await c.create_billing_portal_session()
    assert url == "https://billing.stripe.com/p/session_x"
    req = route.calls.last.request
    assert req.url.path == "/v1/billing/portal"
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"


@respx.mock
async def test_list_plans_returns_plan_info():
    respx.get(f"{_GW}/v1/billing/plans").mock(return_value=httpx.Response(200, json=[
        {"id": "free", "name": "Free", "price": 0.0, "interval": "monthly",
         "features": {}, "limits": {"tokens": 1000}},
        {"id": "pro", "name": "Pro", "price": 9.0, "interval": "monthly",
         "features": {"a": True}, "limits": {}}]))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    plans = await c.list_plans()
    assert [p.id for p in plans] == ["free", "pro"]
    assert plans[1].price == 9.0 and plans[0].limits == {"tokens": 1000}


@respx.mock
async def test_list_plans_safe_degrades_to_empty_list():
    respx.get(f"{_GW}/v1/billing/plans").mock(return_value=httpx.Response(503))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    assert await c.list_plans() == []


@respx.mock
async def test_get_auto_topup_parses_settings():
    route = respx.get(f"{_GW}/v1/billing/auto-topup").mock(return_value=httpx.Response(200,
        json={"enabled": True, "threshold_pct": 15, "recharge_tokens": 30000,
              "recharge_cents": 3000, "payment_method_id": "pm_9"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    s = await c.get_auto_topup()
    assert s.enabled is True and s.threshold_pct == 15 and s.payment_method_id == "pm_9"
    req = route.calls.last.request
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"


@respx.mock
async def test_get_auto_topup_safe_degrades_to_defaults():
    respx.get(f"{_GW}/v1/billing/auto-topup").mock(return_value=httpx.Response(500))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    s = await c.get_auto_topup()
    assert s.enabled is False and s.threshold_pct == 10 and s.recharge_tokens == 20000


@respx.mock
async def test_set_auto_topup_puts_body_with_acting_user():
    route = respx.put(f"{_GW}/v1/billing/auto-topup").mock(return_value=httpx.Response(200,
        json={"status": "ok"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    ok = await c.set_auto_topup(enabled=True, threshold_pct=20, recharge_tokens=40000,
                                payment_method_id="pm_5")
    assert ok is True
    req = route.calls.last.request
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"
    assert json.loads(req.content) == {"enabled": True, "threshold_pct": 20,
                                       "recharge_tokens": 40000, "payment_method_id": "pm_5"}


@respx.mock
async def test_cancel_subscription_posts_and_returns_dict():
    route = respx.post(f"{_GW}/v1/billing/cancel").mock(return_value=httpx.Response(200,
        json={"status": "canceled", "effective_at": "2026-07-01"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    res = await c.cancel_subscription()
    assert res == {"status": "canceled", "effective_at": "2026-07-01"}
    req = route.calls.last.request
    assert req.url.path == "/v1/billing/cancel"
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"


@respx.mock
async def test_resume_subscription_posts_and_returns_dict():
    route = respx.post(f"{_GW}/v1/billing/resume").mock(return_value=httpx.Response(200,
        json={"status": "active", "plan": "pro", "expires_at": "2026-08-01",
              "cancel_at_period_end": False}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    res = await c.resume_subscription()
    assert res == {"status": "active", "plan": "pro", "expires_at": "2026-08-01",
                   "cancel_at_period_end": False}
    req = route.calls.last.request
    assert req.url.path == "/v1/billing/resume"
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"


@respx.mock
async def test_get_subscription_parses_cancel_at_period_end():
    respx.get(f"{_GW}/v1/billing/internal/subscription/imp_u_x").mock(
        return_value=httpx.Response(200, json={"plan": "pro", "status": "active",
            "started_at": "2026-01-01T00:00:00", "expires_at": "2026-08-01",
            "cancel_at_period_end": True}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    sub = await c.get_subscription()
    assert sub.plan == "pro" and sub.status == "active"
    assert sub.cancel_at_period_end is True


@respx.mock
async def test_get_subscription_defaults_cancel_at_period_end_false():
    respx.get(f"{_GW}/v1/billing/internal/subscription/imp_u_x").mock(
        return_value=httpx.Response(200, json={"plan": "free", "status": "active"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    sub = await c.get_subscription()
    assert sub.cancel_at_period_end is False


@respx.mock
async def test_update_billing_profile_puts_profile():
    route = respx.put(f"{_GW}/v1/billing/profile").mock(return_value=httpx.Response(200,
        json={"status": "ok"}))
    c = BillingClient(gateway_url=_GW, service_token="svc", user_id="imp_u_x")
    profile = {"name": "Acme", "company": "Acme Inc", "vat": "EU123", "country": "DE"}
    ok = await c.update_billing_profile(profile)
    assert ok is True
    req = route.calls.last.request
    assert req.url.path == "/v1/billing/profile"
    assert req.headers["X-Service-Token"] == "svc"
    assert req.headers["X-Acting-User"] == "imp_u_x"
    assert json.loads(req.content) == profile
