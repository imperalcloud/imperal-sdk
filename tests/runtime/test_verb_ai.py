import pytest
from imperal_sdk.runtime.verbs import run_ai


class FakeAI:
    async def complete(self, prompt, model="", **kw):
        class R:
            text = f"echo:{prompt}"

        return R()


@pytest.mark.asyncio
async def test_ai_complete_returns_text():
    out = await run_ai({"prompt": "hello"}, FakeAI())
    assert out["text"] == "echo:hello"
