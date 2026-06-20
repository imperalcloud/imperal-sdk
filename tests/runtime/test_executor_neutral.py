"""TDD: executor.py must route _check_target_scope via _platform (engine-neutral)."""
import inspect
import imperal_sdk.runtime.executor as ex


def test_executor_has_no_engine_name():
    src = inspect.getsource(ex)
    assert "imperal_kernel" not in src, "executor.py must route through _platform, not name the engine"


def test_check_target_scope_still_exported_and_delegates():
    assert hasattr(ex, "_check_target_scope")
    # In a no-kernel env it returns the platform fallback dict (allowed=False).
    out = ex._check_target_scope(target_user_id="u1")
    assert out["allowed"] is False
