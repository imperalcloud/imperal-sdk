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
