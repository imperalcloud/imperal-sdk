import pytest
from imperal_sdk.types.action_result import ActionResult
from imperal_sdk.ui.actions import Call


def test_action_result_time_travel_and_ledger():
    # Создаем результат действия с поддержкой отката (undo), дифа и квитанции
    undo_action = Call("set_status", status="idle")
    diff_payload = {"status": ("idle", "running")}
    receipt_hash = "rcpt_98fbc12a3d"

    res = ActionResult.success(
        data={"server": "srv-01", "status": "running"},
        summary="Server started",
        undo=undo_action,
        diff=diff_payload,
        action_receipt=receipt_hash,
    )

    d = res.to_dict()
    assert d["status"] == "success"
    assert d["summary"] == "Server started"
    assert d["undo"] == {"action": "call", "function": "set_status", "params": {"status": "idle"}}
    assert d["diff"] == {"status": ("idle", "running")}
    assert d["action_receipt"] == receipt_hash
