"""Task D1 — KernelEngine ABC tests."""
import pytest
from imperal_sdk.runtime.engine import KernelEngine


def test_kernel_engine_is_abstract():
    with pytest.raises(TypeError):
        KernelEngine()  # cannot instantiate the ABC


def test_importable_from_package():
    import imperal_sdk
    assert hasattr(imperal_sdk, "KernelEngine")
