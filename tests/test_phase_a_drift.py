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
    # Kernel hub_dispatch depth is admin-tunable (default 6); its depth counter
    # excludes the root, so the default allows 6 nested inter-extension calls.
    # The SDK call_stack INCLUDES the root, so the matching fallback cap is
    # kernel-allowed-calls + 1 == 7 (reject at len(call_stack) >= MAX_CALL_DEPTH).
    # Coordinated with the live kernel default (2026-05-31 admin-tunable deploy).
    KERNEL_ALLOWED_NESTED_CALLS = 6
    assert client.MAX_CALL_DEPTH == KERNEL_ALLOWED_NESTED_CALLS + 1  # == 7


def test_every_mock_implements_its_whole_protocol():
    """Each Mock* must cover ALL of its protocol, names AND signatures.

    Written after MockBilling was found implementing 4 of BillingProtocol's 19
    methods, which made `Context(billing=MockBilling())` fail a type check —
    extensions touching billing could not write a typed unit test with the SDK's
    own testing kit. The drift went unnoticed because the only guard here
    (test_billing_track_usage_matches_client) inspected a single method.

    This checks every pair, so the next omission fails on the spot instead of
    surfacing months later as someone's broken example.
    """
    import imperal_sdk.context as ctxmod
    import imperal_sdk.testing.mock_context as mockmod

    PAIRS = [
        ("StoreProtocol", "MockStore"),
        ("AIProtocol", "MockAI"),
        ("BillingProtocol", "MockBilling"),
        ("NotifyProtocol", "MockNotify"),
        ("StorageProtocol", "MockStorage"),
        ("HTTPProtocol", "MockHTTP"),
        ("ConfigProtocol", "MockConfig"),
        ("SkeletonProtocol", "MockSkeleton"),
    ]

    def public_methods(cls):
        return {
            n for n, _ in inspect.getmembers(cls, inspect.isfunction)
            if not n.startswith("_")
        }

    problems: list[str] = []
    for proto_name, mock_name in PAIRS:
        proto = getattr(ctxmod, proto_name, None)
        mock = getattr(mockmod, mock_name, None)
        if proto is None or mock is None:      # pair renamed/removed
            problems.append(f"{proto_name}/{mock_name}: not found")
            continue

        missing = sorted(public_methods(proto) - public_methods(mock))
        if missing:
            problems.append(f"{mock_name} is missing {missing}")

        # A method present but with the wrong parameters is just as broken as
        # a missing one — callers type-check against the protocol signature.
        for name in sorted(public_methods(proto) & public_methods(mock)):
            p = list(inspect.signature(getattr(proto, name)).parameters)
            m = list(inspect.signature(getattr(mock, name)).parameters)
            if p != m:
                problems.append(f"{mock_name}.{name} signature {m} != protocol {p}")

    assert not problems, "mock/protocol drift:\n  " + "\n  ".join(problems)


def test_mock_billing_satisfies_protocol():
    """The runtime check the type checker mirrors."""
    assert isinstance(MockBilling(), BillingProtocol)


def test_billing_protocol_declares_its_return_types():
    """No BillingProtocol method may go unannotated.

    Four methods (create_setup_intent, change_plan, topup, get_auto_topup) had
    no return annotation, so a checker inferred None — and every honest client
    returning a real result object was reported incompatible with the protocol
    it actually satisfies. An unannotated `...` stub reads as deliberate, which
    is exactly why nobody caught it by eye.
    """
    unannotated = [
        name
        for name, fn in inspect.getmembers(BillingProtocol, inspect.isfunction)
        if not name.startswith("_")
        and inspect.signature(fn).return_annotation is inspect.Signature.empty
    ]
    assert not unannotated, f"BillingProtocol methods without a return type: {unannotated}"
