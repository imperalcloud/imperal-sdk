# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Phase 4 Task 4.3 — ``@ext.cache_model`` decorator.

These tests import ``imperal_sdk.extension.Extension`` and therefore require
Python >= 3.11 (PEP 604 unions in the package chain). Smoke-run on 3.9 will
fail at import time.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from imperal_sdk.extension import Extension


def test_cache_model_registers():
    ext = Extension(app_id="mail")

    @ext.cache_model("inbox_summary")
    class InboxSummary(BaseModel):
        unread: int
        latest_subject: str = ""

    assert "inbox_summary" in ext._cache_models
    assert ext._cache_models["inbox_summary"] is InboxSummary


def test_cache_model_duplicate_raises():
    ext = Extension(app_id="mail")

    @ext.cache_model("inbox_summary")
    class A(BaseModel):
        x: int

    with pytest.raises(ValueError, match="already registered"):
        @ext.cache_model("inbox_summary")
        class B(BaseModel):
            y: int


def test_cache_model_non_pydantic_raises():
    ext = Extension(app_id="mail")

    with pytest.raises(TypeError, match="Pydantic BaseModel"):
        @ext.cache_model("bogus")
        class NotAModel:
            pass


def test_cache_model_non_class_raises():
    ext = Extension(app_id="mail")

    with pytest.raises(TypeError, match="Pydantic BaseModel"):
        ext.cache_model("bogus")(lambda: 1)


def test_cache_model_two_extensions_independent():
    mail = Extension(app_id="mail")
    sharelock = Extension(app_id="sharelock-v2")

    @mail.cache_model("summary")
    class MailSummary(BaseModel):
        unread: int

    @sharelock.cache_model("summary")
    class CaseSummary(BaseModel):
        case_id: str

    assert mail._cache_models["summary"] is MailSummary
    assert sharelock._cache_models["summary"] is CaseSummary
    assert mail._cache_models["summary"] is not sharelock._cache_models["summary"]


def test_resolve_cache_model_name():
    ext = Extension(app_id="mail")

    @ext.cache_model("inbox_summary")
    class InboxSummary(BaseModel):
        unread: int

    assert ext._resolve_cache_model_name(InboxSummary) == "inbox_summary"


def test_resolve_cache_model_name_unregistered_returns_none():
    ext = Extension(app_id="mail")

    class Unregistered(BaseModel):
        x: int = 1

    assert ext._resolve_cache_model_name(Unregistered) is None


def test_resolve_cache_model_name_same_name_different_class_in_other_ext():
    mail = Extension(app_id="mail")
    sharelock = Extension(app_id="sharelock-v2")

    @mail.cache_model("shared_name")
    class A(BaseModel):
        x: int = 1

    @sharelock.cache_model("shared_name")
    class B(BaseModel):
        y: int = 2

    assert mail._resolve_cache_model_name(A) == "shared_name"
    assert mail._resolve_cache_model_name(B) is None
    assert sharelock._resolve_cache_model_name(A) is None
    assert sharelock._resolve_cache_model_name(B) == "shared_name"
