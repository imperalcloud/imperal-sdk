# -*- coding: utf-8 -*-
import pytest
from imperal_sdk import ui
from imperal_sdk.ui.stage import Stage

def test_stage_initialization():
    stage = Stage(
        id="test-cluster-hud",
        title="Cluster Telemetry",
        content=ui.Stat(label="Health", value="100%", color="green"),
        hotkeys={"1": "rebalance", "q": "quit"},
        receipt=lambda res: f"ceph.rebalanced: {res["freed"]} freed ✓",
        command="ceph.cluster"
    )

    d = stage.to_dict()
    assert d["type"] == "Stage"
    assert d["props"]["id"] == "test-cluster-hud"
    assert d["props"]["title"] == "Cluster Telemetry"
    assert d["props"]["command"] == "ceph.cluster"
    assert d["props"]["hotkeys"] == {"1": "rebalance", "q": "quit"}
    assert len(d["children"]) == 1
    assert d["children"][0]["type"] == "Stat"

def test_stage_receipt_generation():
    stage = Stage(
        id="proxy-redirect",
        title="Redirect Rules",
        receipt=lambda res: f"proxy.redirect: {res["from"]} -> {res["to"]} [42ms] ✓"
    )
    receipt_str = stage.generate_receipt({"from": "/blackfriday", "to": "/pricing"})
    assert receipt_str == "proxy.redirect: /blackfriday -> /pricing [42ms] ✓"

def test_stage_default_receipt_generation():
    stage = Stage(
        id="cache-clear",
        title="Clear Buffer Cache",
        command="sys.cache"
    )
    receipt_str = stage.generate_receipt(delta="18GB released", duration_ms=120)
    assert receipt_str == "❯ sys.cache: 18GB released ── [120ms] ✓"
