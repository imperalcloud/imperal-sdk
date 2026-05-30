import json
import pathlib

CONTRACT = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "contract" / "kernel-contract.sample.json"


def test_sample_contract_has_required_sections():
    c = json.loads(CONTRACT.read_text())
    for key in ("version", "request_models", "constants",
                "sdk_version_floor", "consumed_decorator_fields", "ctx_surface"):
        assert key in c, f"contract missing top-level section: {key}"
    # the depth constant must carry SEMANTICS, never a bare number
    md = c["constants"]["hub_dispatch"]["max_depth"]
    assert set(md) >= {"value", "counts_root", "effective_nested_calls"}
    # the billing usage request model must name the real field 'quantity'
    um = c["request_models"]["POST /v1/billing/internal/usage/track"]["fields"]
    assert "quantity" in um and "amount" not in um
