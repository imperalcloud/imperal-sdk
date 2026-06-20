# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""Tests for curated declarative_capable + action_vocab_safe catalog flags.

Real catalog keys verified against sdk-reference.json (2026-06-20):
  - ui.Call, ui.Navigate, ui.Send, ui.Open  — confirmed present
  - ctx.http.get                              — confirmed present (non-safe example)
  - ctx.store.get/list/create/update/delete  — confirmed present
  - ctx.ai.complete                          — confirmed present
"""
from imperal_sdk.devtools.generate_reference import generate_reference


def test_every_symbol_has_flags() -> None:
    """All symbols must carry both flag keys regardless of value."""
    syms = generate_reference()["symbols"]
    for name, sym in syms.items():
        assert "action_vocab_safe" in sym, f"{name}: missing action_vocab_safe"
        assert "declarative_capable" in sym, f"{name}: missing declarative_capable"
        assert isinstance(sym["action_vocab_safe"], bool), name
        assert isinstance(sym["declarative_capable"], bool), name


def test_action_verbs_are_action_safe() -> None:
    """ui action factories must be flagged action_vocab_safe=True."""
    syms = generate_reference()["symbols"]
    for verb in ("ui.Call", "ui.Navigate", "ui.Send", "ui.Open"):
        assert verb in syms, f"catalog missing expected verb: {verb}"
        assert syms[verb]["action_vocab_safe"] is True, verb
        assert syms[verb]["declarative_capable"] is True, verb


def test_ctx_store_verbs_are_action_safe() -> None:
    """ctx.store CRUD methods must be flagged action_vocab_safe=True."""
    syms = generate_reference()["symbols"]
    for verb in (
        "ctx.store.get", "ctx.store.list",
        "ctx.store.create", "ctx.store.update", "ctx.store.delete",
    ):
        assert verb in syms, f"catalog missing expected verb: {verb}"
        assert syms[verb]["action_vocab_safe"] is True, verb


def test_ctx_ai_complete_is_action_safe() -> None:
    syms = generate_reference()["symbols"]
    assert "ctx.ai.complete" in syms
    assert syms["ctx.ai.complete"]["action_vocab_safe"] is True


def test_arbitrary_method_not_action_safe() -> None:
    """A non-step client method must NOT be in the declarative vocabulary."""
    syms = generate_reference()["symbols"]
    # ctx.http.get is a real catalog key (confirmed by grep)
    assert "ctx.http.get" in syms
    assert syms["ctx.http.get"]["action_vocab_safe"] is False
    assert syms["ctx.http.get"]["declarative_capable"] is False


def test_non_vocab_symbols_not_action_safe() -> None:
    """Spot-check: sdl roles, decorators, dataclasses — all False."""
    syms = generate_reference()["symbols"]
    for name in ("sdl.Entity", "chat.function", "ActionResult", "ctx.billing.get_balance"):
        assert syms[name]["action_vocab_safe"] is False, name
        assert syms[name]["declarative_capable"] is False, name
