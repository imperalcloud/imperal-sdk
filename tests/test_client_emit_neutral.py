"""Source-level neutrality gate: emit() must not name the engine or store.

After the refactor, emit() routes through _platform helpers — no
imperal_kernel or get_shared_redis token may appear in its source.
"""
import inspect
from imperal_sdk.extensions.client import ExtensionsClient


def test_emit_source_has_no_engine_name():
    src = inspect.getsource(ExtensionsClient.emit)
    assert "imperal_kernel" not in src and "get_shared_redis" not in src, (
        "emit() must route through _platform, not name the engine/store"
    )
