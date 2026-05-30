"""Phase A drift tests — Task 7: BillingProtocol + MockBilling.track_usage alignment.

Source of truth: auth-gateway billing/schemas.py UsageTrackRequest (field: quantity, not amount)
    async def track_usage(self, meter: str, quantity: int = 1, user: Any = None) -> bool:
"""
import inspect
from imperal_sdk.context import BillingProtocol
from imperal_sdk.testing.mock_context import MockBilling


def test_billing_track_usage_matches_client():
    sig = inspect.signature(BillingProtocol.track_usage)
    params = list(sig.parameters)
    assert params[1] == "meter"            # (self, meter, quantity=1, user=None)
    assert sig.parameters["quantity"].default == 1
    assert "user" in sig.parameters
    msig = inspect.signature(MockBilling.track_usage)
    assert list(msig.parameters)[1] == "meter"
    assert msig.parameters["quantity"].default == 1
    assert "user" in msig.parameters


def test_config_require_removed():
    from imperal_sdk.context import ConfigProtocol
    from imperal_sdk.testing.mock_context import MockConfig
    assert not hasattr(ConfigProtocol, "require")
    assert not hasattr(MockConfig, "require")
    assert hasattr(ConfigProtocol, "get") and hasattr(ConfigProtocol, "all")


def test_mock_skeleton_is_read_only():
    from imperal_sdk.testing.mock_context import MockSkeleton
    assert not hasattr(MockSkeleton, "update")   # client/protocol read-only since v1.6.0
    assert hasattr(MockSkeleton, "_seed")        # test-only loader


async def test_mock_skeleton_seed_then_get():
    from imperal_sdk.testing.mock_context import MockSkeleton
    s = MockSkeleton()
    s._seed("rules", {"x": 1})
    assert await s.get("rules") == {"x": 1}


def test_mock_skeleton_satisfies_protocol():
    from imperal_sdk.context import SkeletonProtocol
    from imperal_sdk.testing.mock_context import MockSkeleton
    assert isinstance(MockSkeleton(), SkeletonProtocol)


def test_max_call_depth_matches_kernel():
    from imperal_sdk.extensions import client
    # Kernel hub_dispatch_handler.MAX_DEPTH=3 allows 3 nested inter-extension
    # calls (its depth counter excludes the root). The SDK call_stack INCLUDES
    # the root, so the matching cap is kernel-allowed-calls + 1 == 4 (reject at
    # len(call_stack) >= MAX_CALL_DEPTH). Verified against live kernel
    # orchestration/hub_dispatch_handler.py (2026-05-30 kernel-truth pass).
    KERNEL_ALLOWED_NESTED_CALLS = 3
    assert client.MAX_CALL_DEPTH == KERNEL_ALLOWED_NESTED_CALLS + 1  # == 4
