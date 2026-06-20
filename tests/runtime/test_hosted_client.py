"""Tests for HostedClient — injected-transport server-side IR dispatcher."""
import pytest
from imperal_sdk.runtime.hosted_client import HostedClient


@pytest.mark.asyncio
async def test_hosted_client_delegates_to_transport():
    seen = {}

    async def fake_dispatch(ir_fn, params):
        seen["fn"] = ir_fn["name"]
        seen["params"] = params
        return {"steps": {"s1": {"action": "send", "message": "ok"}}}

    eng = HostedClient(dispatch=fake_dispatch)
    out = await eng.run_function(
        {"name": "greet", "impl": {"kind": "declarative", "steps": []}},
        {"who": "V"},
        ctx=None,
    )
    assert seen["fn"] == "greet"
    assert seen["params"] == {"who": "V"}
    assert out["steps"]["s1"]["message"] == "ok"
