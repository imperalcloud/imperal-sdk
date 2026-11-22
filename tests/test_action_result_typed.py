"""Tests for ActionResult[T] with Generic typing."""
import pytest
from pydantic import BaseModel
from imperal_sdk.types.action_result import ActionResult


class DealData(BaseModel):
    deal_id: str
    name: str
    value: float


class TestActionResultSuccess:
    def test_success_with_dict(self):
        r = ActionResult.success(data={"id": "123"}, summary="Created")
        assert r.status == "success"
        assert r.data == {"id": "123"}
        assert r.summary == "Created"
        assert r.error is None
        assert r.retryable is False

    def test_success_with_pydantic(self):
        deal = DealData(deal_id="d1", name="Big Deal", value=50000.0)
        r = ActionResult.success(data=deal, summary="Deal created")
        assert r.status == "success"
        assert r.data == deal
        assert r.data.deal_id == "d1"
        assert r.data.value == 50000.0

    def test_success_summary_required(self):
        r = ActionResult.success(data={}, summary="Done")
        assert r.summary == "Done"


class TestActionResultError:
    def test_error_basic(self):
        r = ActionResult.error("Something broke")
        assert r.status == "error"
        assert r.error == "Something broke"
        assert r.data == {}
        assert r.retryable is False

    def test_error_retryable(self):
        r = ActionResult.error("Timeout", retryable=True)
        assert r.retryable is True


class TestActionResultToDict:
    def test_dict_data(self):
        r = ActionResult.success(data={"id": "1", "name": "test"}, summary="OK")
        d = r.to_dict()
        assert d["status"] == "success"
        assert d["data"] == {"id": "1", "name": "test"}
        assert d["summary"] == "OK"
        assert "error" not in d
        assert "retryable" not in d

    def test_pydantic_data_serialized(self):
        deal = DealData(deal_id="d1", name="Big Deal", value=50000.0)
        r = ActionResult.success(data=deal, summary="Created")
        d = r.to_dict()
        assert d["data"] == {"deal_id": "d1", "name": "Big Deal", "value": 50000.0}
        assert isinstance(d["data"], dict)

    def test_error_includes_fields(self):
        r = ActionResult.error("fail", retryable=True)
        d = r.to_dict()
        assert d["error"] == "fail"
        assert d["retryable"] is True

    def test_from_dict_roundtrip(self):
        original = ActionResult.success(data={"x": 1}, summary="ok")
        d = original.to_dict()
        restored = ActionResult.from_dict(d)
        assert restored.status == original.status
        assert restored.data == original.data
        assert restored.summary == original.summary


class TestActionResultEdgeCases:
    def test_empty_data(self):
        r = ActionResult.success(data={}, summary="Nothing")
        assert r.to_dict()["data"] == {}

    def test_nested_data(self):
        r = ActionResult.success(
            data={"items": [{"id": 1}, {"id": 2}], "total": 2},
            summary="Found 2",
        )
        assert r.to_dict()["data"]["total"] == 2

    def test_error_has_empty_summary(self):
        r = ActionResult.error("broke")
        assert r.summary == ""


class TestActionResultNeedsHuman:
    @pytest.mark.parametrize(
        "code,expected_kind",
        [
            ("PERMISSION_DENIED", "means"),
            ("AUTH_EXPIRED", "means"),
            ("MFA_REQUIRED", "means"),
            ("CONSENT_REQUIRED", "decision"),
            ("PAYMENT_REQUIRED", "decision"),
        ],
    )
    def test_auto_marks_human_action_codes(self, code, expected_kind):
        r = ActionResult.error("Action requires user step", code=code)
        assert r.error_code == code
        assert r.needs_human == {
            "what": "Action requires user step",
            "kind": expected_kind,
        }
        d = r.to_dict()
        assert d["error_code"] == code
        assert d["needs_human"] == {
            "what": "Action requires user step",
            "kind": expected_kind,
        }
        restored = ActionResult.from_dict(d)
        assert restored.error_code == code
        assert restored.needs_human == r.needs_human

    @pytest.mark.parametrize(
        "code",
        [
            "",
            "VALIDATION_MISSING_FIELD",
            "BACKEND_TIMEOUT",
            "BACKEND_5XX",
            "RATE_LIMITED",
            "INTERNAL",
            "EXT_UNSTRUCTURED_ERROR",
            "CUSTOM_APP_CODE",
        ],
    )
    def test_does_not_auto_mark_non_human_codes(self, code):
        r = ActionResult.error("Some error", code=code)
        assert r.needs_human is None
        d = r.to_dict()
        assert "needs_human" not in d

    def test_explicit_needs_human_overrides_default(self):
        explicit = {"what": "Reconnect Gmail OAuth in Integrations", "kind": "means"}
        r = ActionResult.error(
            "401 Unauthorized",
            code="AUTH_EXPIRED",
            needs_human=explicit,
        )
        assert r.needs_human == explicit
        # Mutating caller dict does not mutate ActionResult
        explicit["what"] = "mutated"
        assert r.needs_human["what"] == "Reconnect Gmail OAuth in Integrations"

    def test_explicit_needs_human_allowed_on_custom_code(self):
        r = ActionResult.error(
            "Multiple projects match 'prod'",
            code="AMBIGUOUS_PROJECT",
            needs_human={"what": "Choose which project: prod-eu or prod-us", "kind": "decision"},
        )
        assert r.needs_human == {
            "what": "Choose which project: prod-eu or prod-us",
            "kind": "decision",
        }
        restored = ActionResult.from_dict(r.to_dict())
        assert restored.needs_human == r.needs_human

    def test_from_dict_auto_marks_when_human_code_present_without_needs_human(self):
        restored = ActionResult.from_dict(
            {
                "status": "error",
                "error": "2FA code required",
                "error_code": "MFA_REQUIRED",
            }
        )
        assert restored.needs_human == {"what": "2FA code required", "kind": "means"}
