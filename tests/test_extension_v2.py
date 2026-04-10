# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for Extension v2 decorators — lifecycle, health, webhook, events, expose."""
import pytest
from imperal_sdk.extension import (
    Extension, LifecycleHook, HealthCheckDef, WebhookDef,
    EventHandlerDef, ExposedMethod,
)


class TestLifecycleHooks:
    def test_on_install(self):
        ext = Extension("test-app")
        @ext.on_install
        async def setup(ctx): pass
        assert "on_install" in ext.lifecycle
        assert ext.lifecycle["on_install"].func is setup

    def test_on_upgrade(self):
        ext = Extension("test-app")
        @ext.on_upgrade("0.9.0")
        async def migrate(ctx): pass
        assert "on_upgrade:0.9.0" in ext.lifecycle
        assert ext.lifecycle["on_upgrade:0.9.0"].version == "0.9.0"

    def test_on_uninstall(self):
        ext = Extension("test-app")
        @ext.on_uninstall
        async def cleanup(ctx): pass
        assert "on_uninstall" in ext.lifecycle

    def test_on_enable_disable(self):
        ext = Extension("test-app")
        @ext.on_enable
        async def enable(ctx): pass
        @ext.on_disable
        async def disable(ctx): pass
        assert "on_enable" in ext.lifecycle
        assert "on_disable" in ext.lifecycle


class TestHealthCheck:
    def test_register(self):
        ext = Extension("test-app")
        @ext.health_check
        async def check(ctx): pass
        assert ext._health_check is not None
        assert ext._health_check.func is check

    def test_no_health_check_by_default(self):
        ext = Extension("test-app")
        assert ext._health_check is None


class TestWebhook:
    def test_register(self):
        ext = Extension("test-app")
        @ext.webhook("/stripe", method="POST", secret_header="Stripe-Signature")
        async def handle(ctx, request): pass
        assert "/stripe" in ext.webhooks
        wh = ext.webhooks["/stripe"]
        assert wh.method == "POST"
        assert wh.secret_header == "Stripe-Signature"
        assert wh.func is handle

    def test_multiple_webhooks(self):
        ext = Extension("test-app")
        @ext.webhook("/stripe")
        async def h1(ctx, req): pass
        @ext.webhook("/github")
        async def h2(ctx, req): pass
        assert len(ext.webhooks) == 2


class TestOnEvent:
    def test_register(self):
        ext = Extension("test-app")
        @ext.on_event("email.received")
        async def handle(ctx, event): pass
        assert len(ext.event_handlers) == 1
        assert ext.event_handlers[0].event_type == "email.received"

    def test_multiple_handlers(self):
        ext = Extension("test-app")
        @ext.on_event("email.received")
        async def h1(ctx, event): pass
        @ext.on_event("deal.created")
        async def h2(ctx, event): pass
        assert len(ext.event_handlers) == 2


class TestExpose:
    def test_register(self):
        ext = Extension("test-app")
        @ext.expose("get_deal", action_type="read")
        async def get_deal(ctx, params): pass
        assert "get_deal" in ext.exposed
        assert ext.exposed["get_deal"].action_type == "read"

    def test_default_action_type(self):
        ext = Extension("test-app")
        @ext.expose("list_items")
        async def list_items(ctx): pass
        assert ext.exposed["list_items"].action_type == "read"

    def test_write_action_type(self):
        ext = Extension("test-app")
        @ext.expose("create_deal", action_type="write")
        async def create(ctx, params): pass
        assert ext.exposed["create_deal"].action_type == "write"


class TestDecoratorPreservesFunction:
    def test_all_decorators_return_original(self):
        ext = Extension("test-app")

        @ext.on_install
        async def install(ctx): return "installed"

        @ext.health_check
        async def health(ctx): return "ok"

        @ext.webhook("/test")
        async def wh(ctx, req): return "handled"

        @ext.on_event("test.event")
        async def ev(ctx, event): return "received"

        @ext.expose("test_method")
        async def exposed(ctx): return "exposed"

        # All decorators should return the original function
        assert install.__name__ == "install"
        assert health.__name__ == "health"
        assert wh.__name__ == "wh"
        assert ev.__name__ == "ev"
        assert exposed.__name__ == "exposed"
