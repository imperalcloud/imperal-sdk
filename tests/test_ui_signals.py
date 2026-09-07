import pytest
import asyncio
from imperal_sdk.ui.signals import Signal, UISignal
from imperal_sdk.ui.base import _serialize, UINode
from imperal_sdk.ui import data
from imperal_sdk.context import Context
from imperal_sdk.types.identity import UserContext
from imperal_sdk.signals.client import SignalsClient


def test_ui_signal_creation_and_serialization():
    sig = Signal("cluster:status", default="ready")
    assert isinstance(sig, UISignal)
    assert sig.key == "cluster:status"
    assert sig.default == "ready"
    
    serialized = _serialize(sig)
    assert serialized == {
        "__type__": "signal",
        "key": "cluster:status",
        "default": "ready",
    }


def test_ui_node_with_signal_props():
    badge = data.Badge(
        label=Signal("task:count", default=0),
        color=Signal("task:color", default="gray"),
    )
    d = badge.to_dict()
    assert d["type"] == "Badge"
    assert d["props"]["label"] == {
        "__type__": "signal",
        "key": "task:count",
        "default": 0,
    }
    assert d["props"]["color"] == {
        "__type__": "signal",
        "key": "task:color",
        "default": "gray",
    }


@pytest.mark.asyncio
async def test_signals_client_local_dispatch():
    client = SignalsClient()
    received = []

    async def on_signal(key, val):
        received.append((key, val))

    client.subscribe("server:cpu", on_signal)
    res = await client.emit("server:cpu", 85.5, host="srv-1")
    assert res["ok"] is True
    assert res["key"] == "server:cpu"
    assert len(received) == 1
    assert received[0] == ("server:cpu", 85.5)


def test_context_signals_property():
    user = UserContext(imperal_id="imp_u_test", email="admin@imperal.io", tenant_id="default", role="admin")
    ctx = Context(user=user)
    assert ctx.signals is not None
    assert isinstance(ctx.signals, SignalsClient)
