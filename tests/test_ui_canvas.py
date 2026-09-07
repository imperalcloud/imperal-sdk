import pytest
from imperal_sdk.ui.canvas import Canvas, CanvasNode, CanvasEdge
from imperal_sdk.ui.actions import Call


def test_canvas_component_serialization():
    node1 = CanvasNode(
        id="srv-auth",
        title="Auth Gateway",
        x=100.0,
        y=150.0,
        type="gateway",
        status="healthy",
        metrics={"rps": 1250, "p99": "4.2ms"},
        on_click=Call("inspect_service", name="auth"),
    )
    node2 = CanvasNode(
        id="srv-db",
        title="PostgreSQL Cluster",
        x=400.0,
        y=150.0,
        type="database",
        status="healthy",
        metrics={"active_conns": 38},
    )
    edge = CanvasEdge(
        from_node="srv-auth",
        to_node="srv-db",
        protocol="pgwire",
        status="active",
        latency_ms=1.1,
        animated=True,
    )

    canvas = Canvas(
        nodes=[node1, node2],
        edges=[edge],
        height=650,
        interactive=True,
        show_minimap=True,
    )

    d = canvas.to_dict()
    assert d["type"] == "Canvas"
    assert d["props"]["height"] == 650
    assert d["props"]["interactive"] is True
    assert d["props"]["show_minimap"] is True
    assert len(d["props"]["nodes"]) == 2
    assert d["props"]["nodes"][0]["id"] == "srv-auth"
    assert d["props"]["nodes"][0]["on_click"]["action"] == "call"
    assert d["props"]["nodes"][0]["on_click"]["function"] == "inspect_service"
    assert len(d["props"]["edges"]) == 1
    assert d["props"]["edges"][0]["from"] == "srv-auth"
    assert d["props"]["edges"][0]["to"] == "srv-db"
    assert d["props"]["edges"][0]["latency_ms"] == 1.1
