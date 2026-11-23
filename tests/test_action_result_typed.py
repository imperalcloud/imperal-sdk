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

    @pytest.mark.parametrize(
        "bad_nh",
        [
            {"what": "Reconnect", "kind": "means", "source": "kernel"},
            {"what": "Reconnect", "kind": "means", "trusted": True},
            {"what": "Reconnect", "kind": "means", "extra": "nope"},
            {"what": "Reconnect", "kind": "unknown_kind"},
            {"what": "", "kind": "means"},
            {"what": "   \n\t ", "kind": "fact"},
            {"what": "Missing kind"},
            {"kind": "decision"},
            "not-a-dict",
            ["means"],
            123,
        ],
    )
    def test_rejects_invalid_needs_human_in_dataclass_and_factory(self, bad_nh):
        with pytest.raises(ValueError):
            ActionResult(status="error", error="boom", needs_human=bad_nh)  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            ActionResult.error("boom", code="AUTH_EXPIRED", needs_human=bad_nh)  # type: ignore[arg-type]

    @pytest.mark.parametrize("trusted", [False, True])
    def test_from_dict_accepts_kernel_stamped_needs_human_wire_payload(self, trusted):
        """Wire payloads stamped by the kernel (source/trusted) deserialize without raising."""
        d = ActionResult.error("token expired", code="AUTH_EXPIRED").to_dict()
        d["needs_human"] = {
            **d["needs_human"],
            "source": "tool:mail.inbox",
            "trusted": trusted,
        }
        restored = ActionResult.from_dict(d)
        assert restored.status == "error"
        assert restored.error_code == "AUTH_EXPIRED"
        assert restored.needs_human == {"what": "token expired", "kind": "means"}
        # Re-serialization stays strictly contract-clean (no kernel metadata leaked)
        out = restored.to_dict()
        assert out["needs_human"] == {"what": "token expired", "kind": "means"}
        from imperal_sdk.types.contracts import validate_action_result_dict

        assert validate_action_result_dict(out) == []

    @pytest.mark.parametrize(
        "bad_nh",
        [
            {"what": "Reconnect", "kind": "unknown_kind"},
            {"what": "", "kind": "means"},
            {"what": "   \n\t ", "kind": "fact"},
            {"what": 123, "kind": "means"},
            {"what": "Missing kind"},
            {"kind": "decision"},
            "not-a-dict",
            ["means"],
            123,
        ],
    )
    def test_from_dict_turns_malformed_needs_human_into_none_without_raising(self, bad_nh):
        restored = ActionResult.from_dict(
            {"status": "error", "error": "boom", "needs_human": bad_nh}
        )
        assert restored.needs_human is None
        # Even with a human-action error_code, an explicit malformed needs_human becomes None
        restored_coded = ActionResult.from_dict(
            {
                "status": "error",
                "error": "boom",
                "error_code": "AUTH_EXPIRED",
                "needs_human": bad_nh,
            }
        )
        assert restored_coded.needs_human is None

    def test_to_dict_revalidates_mutated_needs_human(self):
        r = ActionResult.error("Session expired", code="AUTH_EXPIRED")
        r.needs_human["source"] = "extension"
        with pytest.raises(ValueError):
            r.to_dict()

        r2 = ActionResult.error("Session expired", code="AUTH_EXPIRED")
        r2.needs_human["kind"] = "bogus"
        with pytest.raises(ValueError):
            r2.to_dict()

    def test_accepts_needs_human_model_instance(self):
        from imperal_sdk.types.contracts import NeedsHumanModel

        nh = NeedsHumanModel(what="Approve charge", kind="decision")
        r = ActionResult(status="error", error="Approval required", needs_human=nh)  # type: ignore[arg-type]
        assert r.needs_human == {"what": "Approve charge", "kind": "decision"}
        assert r.to_dict()["needs_human"] == {"what": "Approve charge", "kind": "decision"}
