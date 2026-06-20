"""Engine-parity conformance test (L0-2 success criterion #2).

Proves: the SAME IR function + params yields IDENTICAL results on
LocalDevEngine (in-process) and HostedClient (injected transport that runs
the same run_steps interpreter server-side). Parity is structural at L0-2;
a live-kernel parity run is deferred with the real transport.

If the two engines diverge, the assertion failure identifies which output
differed — do NOT weaken the assertion; investigate which engine is wrong.
"""
from __future__ import annotations

import pytest

from imperal_sdk.runtime.local_engine import LocalDevEngine
from imperal_sdk.runtime.hosted_client import HostedClient
from imperal_sdk.runtime.interpreter import run_steps


IR_FN = {
    "name": "greet",
    "impl": {
        "kind": "declarative",
        "steps": [
            {"id": "s1", "op": "send", "args": {"message": "hi {{event.who}}"}},
        ],
    },
}


class Ctx:
    store = None
    ai = None
    extensions = None
    current_app_id = "toy"


@pytest.mark.asyncio
async def test_local_and_hosted_produce_identical_results():
    """LocalDevEngine and HostedClient return byte-identical dicts for the same IR fn."""
    local = LocalDevEngine()

    # The hosted transport runs the same interpreter server-side — parity by construction at L0-2.
    async def server_dispatch(ir_fn: dict, params: dict) -> dict:
        return await run_steps(ir_fn["impl"]["steps"], Ctx(), event=params)

    hosted = HostedClient(dispatch=server_dispatch)

    params = {"who": "Val"}
    out_local = await local.run_function(IR_FN, params, Ctx())
    out_hosted = await hosted.run_function(IR_FN, params, Ctx())

    # Both engines must return identical structures.
    assert out_local == out_hosted, (
        f"Engine parity broken!\n  local:  {out_local}\n  hosted: {out_hosted}"
    )

    # And the step result must be the expected directive.
    assert out_local["steps"]["s1"] == {"action": "send", "message": "hi Val"}, (
        f"Unexpected step result: {out_local['steps']['s1']!r}"
    )
