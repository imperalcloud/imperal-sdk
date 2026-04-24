# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Phase 4 spec-review fixes — ``chat/prompt.py`` helper.

Covers the I-CHATEXT-IDENTITY-INTEGRITY-VIA-METADATA path: the system
prompt builder reads ``_capability_boundary`` and ``_icnli_integrity``
from ``ctx._metadata["_context"]``. Missing fragments in prod must emit
a loud WARNING; in dev they drop silently.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from imperal_sdk.chat.prompt import _get_chat_context_fragment


def test_capability_boundary_read_from_metadata():
    ctx = MagicMock()
    ctx._metadata = {
        "_context": {
            "_capability_boundary": {
                "assistant_name": "Webbee",
                "all_capabilities": "- mail\n- notes",
            }
        }
    }
    frag = _get_chat_context_fragment(ctx, "_capability_boundary")
    assert frag["assistant_name"] == "Webbee"
    assert "mail" in frag["all_capabilities"]


def test_icnli_integrity_read_from_metadata():
    ctx = MagicMock()
    ctx._metadata = {
        "_context": {
            "_icnli_integrity": {"rules": ["rule-1", "rule-2"]}
        }
    }
    frag = _get_chat_context_fragment(ctx, "_icnli_integrity")
    assert frag["rules"] == ["rule-1", "rule-2"]


def test_fragment_empty_when_metadata_missing():
    ctx = MagicMock(spec=[])  # no _metadata attr
    assert _get_chat_context_fragment(ctx, "_capability_boundary") == {}


def test_fragment_empty_when_context_bag_missing():
    ctx = MagicMock()
    ctx._metadata = {}
    assert _get_chat_context_fragment(ctx, "_capability_boundary") == {}


def test_fragment_empty_when_key_missing():
    ctx = MagicMock()
    ctx._metadata = {"_context": {"something_else": {"k": "v"}}}
    assert _get_chat_context_fragment(ctx, "_capability_boundary") == {}


def test_fragment_empty_when_metadata_not_dict():
    """Defensive — non-dict ``_metadata`` must not raise at prompt-build time."""
    ctx = MagicMock()
    ctx._metadata = "not a dict"
    assert _get_chat_context_fragment(ctx, "_capability_boundary") == {}


def test_fragment_empty_when_context_not_dict():
    ctx = MagicMock()
    ctx._metadata = {"_context": "not a dict either"}
    assert _get_chat_context_fragment(ctx, "_capability_boundary") == {}


def test_fragment_empty_when_value_not_dict():
    """If kernel populated the slot with a non-dict (bug), fall back to {}."""
    ctx = MagicMock()
    ctx._metadata = {"_context": {"_capability_boundary": "stringified-bug"}}
    assert _get_chat_context_fragment(ctx, "_capability_boundary") == {}


# ---------------------------------------------------------------------------
# Prod-mode WARNING behaviour
# ---------------------------------------------------------------------------


def test_capability_boundary_warns_in_prod_when_missing(monkeypatch, caplog):
    """With IMPERAL_PROD=true, missing ``_capability_boundary`` must emit
    a WARNING naming the key — silent drop of load-bearing security context
    is a federal-grade red flag."""
    monkeypatch.setenv("IMPERAL_PROD", "true")
    caplog.set_level(logging.WARNING, logger="imperal_sdk.chat.prompt")
    ctx = MagicMock()
    ctx._metadata = {}
    frag = _get_chat_context_fragment(ctx, "_capability_boundary")
    assert frag == {}
    assert any(
        "_capability_boundary" in rec.getMessage()
        and rec.levelname == "WARNING"
        for rec in caplog.records
    ), f"no WARNING for missing capability_boundary in prod: {caplog.records!r}"


def test_icnli_integrity_warns_in_prod_when_missing(monkeypatch, caplog):
    monkeypatch.setenv("IMPERAL_PROD", "1")
    caplog.set_level(logging.WARNING, logger="imperal_sdk.chat.prompt")
    ctx = MagicMock()
    ctx._metadata = {"_context": {}}
    frag = _get_chat_context_fragment(ctx, "_icnli_integrity")
    assert frag == {}
    assert any(
        "_icnli_integrity" in rec.getMessage()
        and rec.levelname == "WARNING"
        for rec in caplog.records
    )


def test_capability_boundary_silent_in_dev_when_missing(monkeypatch, caplog):
    """Without IMPERAL_PROD, missing fragment must drop silently (dev UX)."""
    monkeypatch.delenv("IMPERAL_PROD", raising=False)
    caplog.set_level(logging.WARNING, logger="imperal_sdk.chat.prompt")
    ctx = MagicMock()
    ctx._metadata = {}
    frag = _get_chat_context_fragment(ctx, "_capability_boundary")
    assert frag == {}
    assert not any(
        rec.levelname == "WARNING"
        and "_capability_boundary" in rec.getMessage()
        for rec in caplog.records
    )


def test_no_warning_when_fragment_present_in_prod(monkeypatch, caplog):
    """Populated fragment in prod must NOT warn (baseline sanity)."""
    monkeypatch.setenv("IMPERAL_PROD", "true")
    caplog.set_level(logging.WARNING, logger="imperal_sdk.chat.prompt")
    ctx = MagicMock()
    ctx._metadata = {
        "_context": {"_capability_boundary": {"assistant_name": "Webbee"}}
    }
    frag = _get_chat_context_fragment(ctx, "_capability_boundary")
    assert frag["assistant_name"] == "Webbee"
    assert not any(
        rec.levelname == "WARNING" for rec in caplog.records
    )


@pytest.mark.parametrize("flag_value", ["false", "0", "no", "", "FALSE", "No"])
def test_prod_flag_off_variants(monkeypatch, caplog, flag_value):
    """Several 'off' spellings of IMPERAL_PROD must suppress the warning."""
    monkeypatch.setenv("IMPERAL_PROD", flag_value)
    caplog.set_level(logging.WARNING, logger="imperal_sdk.chat.prompt")
    ctx = MagicMock()
    ctx._metadata = {}
    _get_chat_context_fragment(ctx, "_capability_boundary")
    assert not any(rec.levelname == "WARNING" for rec in caplog.records), (
        f"IMPERAL_PROD={flag_value!r} unexpectedly triggered a warning"
    )
