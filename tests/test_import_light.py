# -*- coding: utf-8 -*-
"""5.2.2 — the package root is import-light (PEP 562 lazy surface).

Kernel federal I-SANDBOX-SAFE-LAZY-IMPORTS (live incident 2026-06-10): the
eager root imports pulled httpx (Context / client modules) into EVERY
consumer of ANY submodule — including Temporal workflow code lazily
importing transport-free helpers like ``imperal_sdk.chat.filters``
(httpx._models subclasses urllib.request.Request, restricted inside the
workflow sandbox -> RestrictedWorkflowAccessError -> whole chat turns
crashed).

Contracts:
  1. ``import imperal_sdk`` and ``import imperal_sdk.chat.filters`` must NOT
     load httpx.
  2. The public surface is unchanged: every ``__all__`` name (and the
     root-importable secrets names) resolves lazily to the SAME object the
     defining module exports; submodules stay reachable as root attributes;
     star-import works; unknown names raise AttributeError.
"""
import subprocess
import sys

import imperal_sdk


def _probe(code: str) -> str:
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=120,
    )
    out = (r.stdout or "").strip()
    if r.returncode != 0 and not out:
        out = "PROBE_ERROR: " + (r.stderr or "").strip()[-400:]
    return out


def test_root_import_is_transport_free():
    out = _probe(
        "import imperal_sdk, sys; "
        "print('HTTPX' if 'httpx' in sys.modules else 'CLEAN')"
    )
    assert out == "CLEAN"


def test_chat_filters_import_is_transport_free():
    out = _probe(
        "from imperal_sdk.chat.filters import enforce_os_identity, enforce_response_style; "
        "import sys; print('HTTPX' if 'httpx' in sys.modules else 'CLEAN')"
    )
    assert out == "CLEAN"


def test_version():
    # The import-light root must expose a semver-shaped __version__. Not pinned to
    # a literal so a version bump doesn't require editing this test (the real
    # version-drift guard is sdk_claims._sdk_version in tests/contract).
    v = imperal_sdk.__version__
    assert isinstance(v, str) and v.count(".") == 2


_SECRETS_NAMES = [
    "SecretSpec", "SecretClient", "SecretStatus",
    "SecretNotDeclaredError", "SecretWriteForbidden", "SecretVaultUnavailable",
    "SecretValueTooLarge", "SecretDeclarationConflict",
]


def test_every_public_name_resolves_to_the_defining_object():
    import importlib

    from imperal_sdk import _LAZY_ATTRS

    for name in list(imperal_sdk.__all__) + _SECRETS_NAMES:
        obj = getattr(imperal_sdk, name)
        if name in ("ui", "sdl"):
            assert obj is importlib.import_module(f"imperal_sdk.{name}")
            continue
        src = _LAZY_ATTRS[name]
        assert obj is getattr(importlib.import_module(src), name), name


def test_submodules_reachable_as_root_attributes():
    for sub in ("chat", "context", "errors", "types", "ui", "sdl", "manifest"):
        mod = getattr(imperal_sdk, sub)
        assert mod.__name__ == f"imperal_sdk.{sub}"


def test_star_import_covers_all():
    ns: dict = {}
    exec("from imperal_sdk import *", ns)  # noqa: S102 — surface test
    missing = [n for n in imperal_sdk.__all__ if n not in ns]
    assert not missing, missing


def test_unknown_attribute_raises_attribute_error():
    try:
        imperal_sdk.definitely_not_a_real_name
    except AttributeError:
        pass
    else:
        raise AssertionError("expected AttributeError")


def test_dir_lists_the_surface():
    d = dir(imperal_sdk)
    for name in ("ChatExtension", "Context", "ui", "sdl", "SecretClient"):
        assert name in d
