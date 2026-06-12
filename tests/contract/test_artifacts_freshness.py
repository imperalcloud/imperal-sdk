"""Conformance A8/A9 — committed contract artifacts must match the live SDK.

A8 (audit 2026-06-04, re-validated 2026-06-12): ``sdk_claims.json`` sat at
5.1.0 while the SDK shipped 5.2.0/5.2.1/5.2.2 — the kernel-side
``contract_guard`` freshness layer keyed on the stale pin and the lag was
invisible to every local gate. A9: the docs_guard snapshots
(``api_surface.json`` / ``ctx_surface.json``) had the same hand-copied-rot
failure mode. These tests run under preflight Edge 1 (``tests/contract/``),
so a stale committed artifact turns the one sanctioned gate red locally.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from imperal_sdk.devtools.generate_api_surface import generate_surface
from imperal_sdk.devtools.generate_sdk_claims import generate_claims

REPO = Path(__file__).resolve().parents[2]
# imperal-sdk sits inside the MCP-Configs workspace checkout; standalone
# clones (CI on GitHub) won't have the workspace-level docs_guard inputs.
WORKSPACE_GUARD_INPUTS = REPO.parent / "scripts" / "docs_guard" / "inputs"


def test_committed_sdk_claims_match_generated() -> None:
    committed = json.loads((REPO / "sdk_claims.json").read_text(encoding="utf-8"))
    assert committed == generate_claims(), (
        "sdk_claims.json is stale — regenerate with: "
        "python -m imperal_sdk.devtools.generate_sdk_claims --output sdk_claims.json "
        "(and copy to kernel tools/contract/sdk-claims.json on deploy)"
    )


def test_docs_guard_api_surface_snapshot_fresh() -> None:
    snap = WORKSPACE_GUARD_INPUTS / "api_surface.json"
    if not snap.is_file():
        pytest.skip("workspace docs_guard inputs not present (standalone SDK checkout)")
    committed = json.loads(snap.read_text(encoding="utf-8"))
    live = generate_surface()
    assert {ns: sorted(m) for ns, m in committed.items()} == {
        ns: sorted(m) for ns, m in live.items()
    }, (
        "scripts/docs_guard/inputs/api_surface.json is stale — refresh it from "
        "imperal_sdk.devtools.generate_api_surface (manual-cp rot, conformance A9)"
    )


def _live_ctx_surface() -> set[str]:
    """Public Context surface: dataclass fields + properties + methods.

    Mirrors the original ctx_surface.json snapshot semantics (everything an
    extension author can legitimately write after ``ctx.`` at the top level,
    excluding kernel-injected attrs like ``secrets`` which are not part of
    the dataclass).
    """
    from imperal_sdk.context import Context

    fields = {f.name for f in dataclasses.fields(Context) if not f.name.startswith("_")}
    members = {
        name
        for name, value in vars(Context).items()
        if not name.startswith("_") and (isinstance(value, property) or callable(value))
    }
    return fields | members


def test_kernel_contract_copies_mutually_consistent() -> None:
    """A5: the two local copies of the kernel contract (the SDK contract-test
    fixture and the docs_guard snapshot) must be identical — both are refreshed
    from kernel ``tools/kernel-contract.json`` on a kernel contract change, and
    one-sided rot (e.g. the pre-2026-06-12 state: guard copy carried the old
    max_depth=3 while the fixture carried 6) is exactly how 'ALL GREEN'
    overstates coverage."""
    guard_copy = WORKSPACE_GUARD_INPUTS / "kernel-contract.json"
    if not guard_copy.is_file():
        pytest.skip("workspace docs_guard inputs not present (standalone SDK checkout)")
    fixture = json.loads(
        (REPO / "tests" / "fixtures" / "contract" / "kernel-contract.sample.json").read_text(
            encoding="utf-8"
        )
    )
    assert fixture == json.loads(guard_copy.read_text(encoding="utf-8")), (
        "kernel-contract fixture and docs_guard snapshot diverged — refresh BOTH "
        "from kernel tools/kernel-contract.json (conformance A5)"
    )


def test_docs_guard_ctx_surface_snapshot_fresh() -> None:
    snap = WORKSPACE_GUARD_INPUTS / "ctx_surface.json"
    if not snap.is_file():
        pytest.skip("workspace docs_guard inputs not present (standalone SDK checkout)")
    committed = set(json.loads(snap.read_text(encoding="utf-8")))
    live = _live_ctx_surface()
    assert committed == live, (
        f"scripts/docs_guard/inputs/ctx_surface.json is stale (conformance A9). "
        f"missing_from_snapshot={sorted(live - committed)} "
        f"gone_from_sdk={sorted(committed - live)}"
    )
