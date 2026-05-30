"""Phase A drift tests — Task 7: BillingProtocol + MockBilling.track_usage alignment.

Source of truth: src/imperal_sdk/billing/client.py:110
    async def track_usage(self, meter: str, amount: int = 1, user: Any = None) -> bool:
"""
import inspect
from imperal_sdk.context import BillingProtocol
from imperal_sdk.testing.mock_context import MockBilling


def test_billing_track_usage_matches_client():
    sig = inspect.signature(BillingProtocol.track_usage)
    params = list(sig.parameters)
    assert params[1] == "meter"            # (self, meter, amount=1, user=None)
    assert sig.parameters["amount"].default == 1
    assert "user" in sig.parameters
    msig = inspect.signature(MockBilling.track_usage)
    assert list(msig.parameters)[1] == "meter"
    assert msig.parameters["amount"].default == 1
    assert "user" in msig.parameters
