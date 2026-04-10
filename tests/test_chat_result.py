"""Tests for ChatResult and FunctionCall typed returns."""
import pytest
from imperal_sdk.types.chat_result import ChatResult, FunctionCall
from imperal_sdk.types.action_result import ActionResult


class TestFunctionCall:
    def test_basic(self):
        fc = FunctionCall(
            name="create_deal", params={"name": "Big Deal"},
            action_type="write", success=True,
        )
        assert fc.name == "create_deal"
        assert fc.params == {"name": "Big Deal"}
        assert fc.action_type == "write"
        assert fc.success is True
        assert fc.result is None
        assert fc.intercepted is False
        assert fc.event == ""

    def test_with_result(self):
        result = ActionResult.success(data={"id": "d1"}, summary="Created")
        fc = FunctionCall(
            name="create_deal", params={}, action_type="write",
            success=True, result=result, event="deal.created",
        )
        assert fc.result.status == "success"
        assert fc.event == "deal.created"

    def test_intercepted(self):
        fc = FunctionCall(
            name="delete_deal", params={"deal_id": "d1"},
            action_type="destructive", success=False, intercepted=True,
        )
        assert fc.intercepted is True
        assert fc.success is False


class TestChatResult:
    def test_defaults(self):
        r = ChatResult(response="Hello!")
        assert r.response == "Hello!"
        assert r.handled is False
        assert r.functions_called == []
        assert r.had_successful_action is False
        assert r.message_type == "text"
        assert r.action_meta == {}
        assert r.intercepted is False
        assert r.task_cancelled is False

    def test_with_functions(self):
        fc = FunctionCall(
            name="send_email", params={"to": "a@b.com"},
            action_type="write", success=True, event="email.sent",
        )
        r = ChatResult(
            response="Email sent!", handled=True,
            functions_called=[fc], had_successful_action=True,
            message_type="function_call",
        )
        assert r.handled is True
        assert len(r.functions_called) == 1
        assert r.functions_called[0].name == "send_email"

    def test_intercepted(self):
        r = ChatResult(
            response="Action requires confirmation.",
            intercepted=True, message_type="confirmation",
        )
        assert r.intercepted is True
        assert r.message_type == "confirmation"

    def test_cancelled(self):
        r = ChatResult(response="Task cancelled.", task_cancelled=True)
        assert r.task_cancelled is True


class TestChatResultToDict:
    def test_basic_to_dict(self):
        r = ChatResult(response="Hello")
        d = r.to_dict()
        assert d["response"] == "Hello"
        assert d["_handled"] is False
        assert d["_functions_called"] == []

    def test_functions_serialized(self):
        fc = FunctionCall(
            name="test", params={"a": 1}, action_type="read",
            success=True, result=ActionResult.success({"v": 1}, "ok"),
        )
        r = ChatResult(response="Done", handled=True, functions_called=[fc])
        d = r.to_dict()
        assert len(d["_functions_called"]) == 1
        assert d["_functions_called"][0]["name"] == "test"
        assert d["_functions_called"][0]["success"] is True

    def test_from_dict_roundtrip(self):
        r = ChatResult(response="Hello", handled=True, message_type="function_call")
        d = r.to_dict()
        restored = ChatResult.from_dict(d)
        assert restored.response == r.response
        assert restored.handled == r.handled
        assert restored.message_type == r.message_type
