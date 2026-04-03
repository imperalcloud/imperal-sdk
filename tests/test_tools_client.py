# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import pytest
from imperal_sdk.tools.client import ToolsClient, ToolInfo, ToolResult


@pytest.fixture
def mock_execute():
    """Create a mock execute function that returns predefined results."""
    results = {}

    async def execute_fn(tool_input: dict) -> dict:
        tool_name = tool_input.get("tool_name", "")
        if tool_name in results:
            return results[tool_name]
        return {"response": f"Mock response for {tool_name}"}

    execute_fn.results = results
    return execute_fn


@pytest.fixture
def tools_client(mock_execute):
    return ToolsClient(
        execute_fn=mock_execute,
        user_info={"id": "user-1", "email": "test@test.com", "scopes": ["*"]},
        extension_id="test-ext",
    )


@pytest.mark.asyncio
async def test_discover(tools_client, mock_execute):
    mock_execute.results["discover_tools"] = {
        "response": {
            "tools_found": 1,
            "tools": [{
                "app_id": "sharelock-v2",
                "activity_name": "tool_sharelock_chat",
                "name": "Sharelock Chat",
                "description": "Analyze cases",
                "domains": ["legal"],
                "required_scopes": ["cases.read"],
                "relevance": 0.85,
            }],
        }
    }

    results = await tools_client.discover("case analysis")
    assert len(results) == 1
    assert isinstance(results[0], ToolInfo)
    assert results[0].app_id == "sharelock-v2"
    assert results[0].relevance == 0.85


@pytest.mark.asyncio
async def test_discover_empty(tools_client, mock_execute):
    mock_execute.results["discover_tools"] = {"response": {"tools_found": 0, "tools": []}}
    results = await tools_client.discover("nonexistent")
    assert results == []


@pytest.mark.asyncio
async def test_call(tools_client, mock_execute):
    mock_execute.results["tool_sharelock_chat"] = {"response": "Case 42 analysis complete"}

    result = await tools_client.call("tool_sharelock_chat", {"message": "analyze case 42"})
    assert isinstance(result, ToolResult)
    assert result.response == "Case 42 analysis complete"
    assert result.tool_name == "tool_sharelock_chat"


@pytest.mark.asyncio
async def test_discover_no_execute_fn():
    client = ToolsClient(execute_fn=None)
    results = await client.discover("anything")
    assert results == []


@pytest.mark.asyncio
async def test_call_no_execute_fn():
    client = ToolsClient(execute_fn=None)
    result = await client.call("tool_test", {})
    assert "not initialized" in result.response


def test_tool_info_dataclass():
    info = ToolInfo(app_id="test", activity_name="tool_test", name="Test",
                    description="desc", domains=["test"], required_scopes=["read"], relevance=0.5)
    assert info.app_id == "test"
    assert info.relevance == 0.5


def test_tool_result_dataclass():
    result = ToolResult(response={"data": 1}, app_id="test", tool_name="tool_test")
    assert result.response == {"data": 1}
