import inspect
import imperal_sdk.runtime._platform as P


def test_shim_exposes_neutral_surface():
    assert hasattr(P, "check_target_scope")
    assert hasattr(P, "record_action_via_chokepoint")
    assert hasattr(P, "publish_event_fallback")


def test_shim_source_has_no_engine_name_in_user_facing_strings():
    """Log/warn strings + docstrings must be engine-neutral (no imperal_kernel/redis/temporal)."""
    src = inspect.getsource(P)
    # The guarded import statements themselves may name the module (that is the
    # ONE place the name is allowed — it is required to import it). But no
    # user-facing log/warning string may.
    import re
    for m in re.finditer(r'(?:log\.[a-z]+|warning|getLogger\([^)]*\)\.[a-z]+)\((.*?)\)', src, re.S):
        frag = m.group(1).lower()
        assert "imperal_kernel" not in frag and "redis" not in frag and "temporal" not in frag, frag


def test_check_target_scope_fallback_shape_when_kernel_absent(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "imperal_kernel.pipeline.scope_guard", None)
    out = P.check_target_scope(target_user_id="u1")
    assert out["allowed"] is False
    assert set(out) >= {"allowed", "reason", "target_user_id", "required_scope",
                        "force_confirmation", "cross_user", "verdict"}
