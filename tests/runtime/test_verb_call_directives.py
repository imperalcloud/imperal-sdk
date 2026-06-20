import pytest
from imperal_sdk.runtime.verbs import run_call, make_directive


class FakeExt:
    async def call(self, app_id, method, **params):
        return {"status": "success", "data": {"app": app_id, "m": method, "p": params}}


@pytest.mark.asyncio
async def test_call_routes_through_extensions_protocol():
    out = await run_call({"function": "ping", "params": {"x": 1}}, FakeExt(), current_app_id="toy")
    assert out["data"]["m"] == "ping"
    assert out["data"]["app"] == "toy"


def test_directives_mirror_uiaction_shape():
    assert make_directive("navigate", {"path": "/x"}) == {"action": "navigate", "path": "/x"}
    assert make_directive("send", {"message": "hi"}) == {"action": "send", "message": "hi"}
    assert make_directive("open", {"url": "https://a"}) == {"action": "open", "url": "https://a"}
