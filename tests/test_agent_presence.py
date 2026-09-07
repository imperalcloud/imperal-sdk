import pytest
from imperal_sdk.ui.feedback import Ghost, AgentPresence
from imperal_sdk.ui.display import Text
from imperal_sdk.ui.interactive import Card


def test_ghost_component_serialization():
    card = Card(title="Production Server", content=Text("Online"))
    ghost = Ghost(child=card, reason="Scaling worker nodes...", pulse=True, opacity=0.5)

    d = ghost.to_dict()
    assert d["type"] == "Ghost"
    assert d["props"]["reason"] == "Scaling worker nodes..."
    assert d["props"]["pulse"] is True
    assert d["props"]["opacity"] == 0.5
    assert d["props"]["child"]["type"] == "Card"
    assert d["props"]["child"]["props"]["title"] == "Production Server"


def test_agent_presence_component_serialization():
    presence = AgentPresence(
        status="executing",
        action="Deploying release v5.14.1",
        progress=75,
        avatar="🐝",
    )

    d = presence.to_dict()
    assert d["type"] == "AgentPresence"
    assert d["props"]["status"] == "executing"
    assert d["props"]["action"] == "Deploying release v5.14.1"
    assert d["props"]["progress"] == 75
    assert d["props"]["avatar"] == "🐝"
