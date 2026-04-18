# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for `imperal_sdk.types.client_contracts` — ctx.* HTTP response types.

Covers validation + round-trip for each of the 7 types:
Document, CompletionResult, LimitsResult, SubscriptionInfo, BalanceInfo,
FileInfo, HTTPResponse.
"""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from imperal_sdk.types import (
    BalanceInfo, CompletionResult, Document, FileInfo, HTTPResponse,
    LimitsResult, SubscriptionInfo,
)
from imperal_sdk.types.client_contracts import (
    BALANCE_INFO_SCHEMA, COMPLETION_RESULT_SCHEMA, DOCUMENT_SCHEMA,
    FILE_INFO_SCHEMA, HTTP_RESPONSE_SCHEMA, LIMITS_RESULT_SCHEMA,
    SUBSCRIPTION_INFO_SCHEMA,
    BalanceInfoModel, CompletionResultModel, DocumentModel, FileInfoModel,
    HTTPResponseModel, LimitsResultModel, SubscriptionInfoModel,
    get_balance_info_schema, get_completion_result_schema,
    get_document_schema, get_file_info_schema, get_http_response_schema,
    get_limits_result_schema, get_subscription_info_schema,
    validate_balance_info_dict, validate_completion_result_dict,
    validate_document_dict, validate_file_info_dict,
    validate_http_response_dict, validate_limits_result_dict,
    validate_subscription_info_dict,
)


# === Document ======================================================

def test_DOC_valid_minimal():
    assert validate_document_dict({"id": "d1", "collection": "notes"}) == []


def test_DOC_valid_full():
    assert validate_document_dict({
        "id": "d1", "collection": "notes", "data": {"title": "x"},
        "extension_id": "notes", "tenant_id": "imp_t_abc",
        "created_at": "2026-04-19T00:00:00Z",
        "updated_at": "2026-04-19T00:00:00Z",
    }) == []


def test_DOC2_missing_id():
    issues = validate_document_dict({"collection": "notes"})
    assert any(i.rule == "DOC2" for i in issues)


def test_DOC3_extra_field_forbidden():
    issues = validate_document_dict({"id": "d", "collection": "c", "extra": 1})
    assert any(i.rule == "DOC3" for i in issues)


def test_DOC_roundtrip():
    doc = Document(id="d1", collection="notes", data={"title": "x"},
                   extension_id="notes")
    assert validate_document_dict(asdict(doc)) == []


# === CompletionResult ==============================================

def test_CPL_valid_minimal():
    assert validate_completion_result_dict({"text": "hello"}) == []


def test_CPL_valid_full():
    assert validate_completion_result_dict({
        "text": "hello", "model": "claude-sonnet-4-6",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "stop_reason": "end_turn",
    }) == []


def test_CPL_roundtrip():
    cr = CompletionResult(text="hi", model="claude-haiku-4-5-20251001",
                          usage={"input_tokens": 3})
    assert validate_completion_result_dict(asdict(cr)) == []


# === LimitsResult ==================================================

def test_LIM_valid_minimal():
    assert validate_limits_result_dict({}) == []  # all fields have defaults


def test_LIM_valid_full():
    assert validate_limits_result_dict({
        "allowed": False, "balance": 0, "plan": "free",
        "limits": {"daily_cap": 1000}, "message": "Out of tokens",
    }) == []


def test_LIM_roundtrip():
    lr = LimitsResult(allowed=True, balance=500, plan="pro")
    assert validate_limits_result_dict(asdict(lr)) == []


# === SubscriptionInfo ==============================================

def test_SUB_valid_minimal():
    assert validate_subscription_info_dict({}) == []


def test_SUB_valid_full():
    assert validate_subscription_info_dict({
        "plan_id": "pro", "plan_name": "Professional", "status": "active",
        "period": "monthly",
        "current_period_start": "2026-04-01",
        "current_period_end": "2026-05-01",
    }) == []


def test_SUB_roundtrip():
    s = SubscriptionInfo(plan_id="free", plan_name="Free", status="active")
    assert validate_subscription_info_dict(asdict(s)) == []


# === BalanceInfo ===================================================

def test_BAL_valid():
    assert validate_balance_info_dict({
        "balance": 1000, "plan": "pro", "cap": 10000,
    }) == []


def test_BAL_roundtrip():
    b = BalanceInfo(balance=42, plan="free", cap=100)
    assert validate_balance_info_dict(asdict(b)) == []


# === FileInfo ======================================================

def test_FIL_valid_minimal():
    assert validate_file_info_dict({"path": "a/b.pdf"}) == []


def test_FIL_valid_full():
    assert validate_file_info_dict({
        "path": "cases/6/evidence/doc.pdf",
        "size": 102400,
        "content_type": "application/pdf",
        "created_at": "2026-04-19T00:00:00Z",
        "url": "https://storage.imperal.io/signed/...",
    }) == []


def test_FIL2_missing_path():
    issues = validate_file_info_dict({"size": 100})
    assert any(i.rule == "FIL2" for i in issues)


def test_FIL4_negative_size():
    issues = validate_file_info_dict({"path": "x", "size": -1})
    assert any(i.rule == "FIL4" for i in issues)


def test_FIL_roundtrip():
    f = FileInfo(path="a.pdf", size=1024, content_type="application/pdf")
    assert validate_file_info_dict(asdict(f)) == []


# === HTTPResponse ==================================================

@pytest.mark.parametrize("status,body", [
    (200, {"ok": True}),
    (201, {"id": "x"}),
    (204, ""),
    (400, "Bad Request"),
    (404, "Not Found"),
    (500, {"error": "internal"}),
])
def test_HRS_valid_status_bodies(status, body):
    assert validate_http_response_dict({
        "status_code": status, "body": body, "headers": {},
    }) == []


def test_HRS_valid_list_body():
    assert validate_http_response_dict({
        "status_code": 200, "body": [{"id": 1}, {"id": 2}],
    }) == []


def test_HRS2_missing_status_code():
    issues = validate_http_response_dict({"body": ""})
    assert any(i.rule == "HRS2" for i in issues)


@pytest.mark.parametrize("bad_status", [99, 600, 1000, -1])
def test_HRS4_invalid_status_range(bad_status):
    issues = validate_http_response_dict({"status_code": bad_status, "body": ""})
    assert any(i.rule == "HRS4" for i in issues)


def test_HRS_roundtrip_dict_body():
    # Note: HTTPResponse.body accepts bytes, which JSON can't carry —
    # roundtrip only valid for dict/str/list bodies.
    r = HTTPResponse(status_code=200, body={"ok": True},
                     headers={"content-type": "application/json"})
    assert validate_http_response_dict({
        "status_code": r.status_code, "body": r.body, "headers": r.headers,
    }) == []


# === Schema exports / drift ========================================

@pytest.mark.parametrize("name,fn,const", [
    ("document", get_document_schema, DOCUMENT_SCHEMA),
    ("completion_result", get_completion_result_schema, COMPLETION_RESULT_SCHEMA),
    ("limits_result", get_limits_result_schema, LIMITS_RESULT_SCHEMA),
    ("subscription_info", get_subscription_info_schema, SUBSCRIPTION_INFO_SCHEMA),
    ("balance_info", get_balance_info_schema, BALANCE_INFO_SCHEMA),
    ("file_info", get_file_info_schema, FILE_INFO_SCHEMA),
    ("http_response", get_http_response_schema, HTTP_RESPONSE_SCHEMA),
])
def test_client_schema_file_in_sync(name, fn, const):
    """Constant == fresh export == committed static file."""
    assert const == fn()
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "src" / "imperal_sdk" / "schemas" / f"{name}.schema.json"
    )
    assert schema_path.exists(), f"Missing {schema_path}"
    assert json.loads(schema_path.read_text()) == fn(), (
        f"src/imperal_sdk/schemas/{name}.schema.json is out of sync"
    )


# === Pydantic models smoke =========================================

def test_all_client_pydantic_models_load():
    """All models build and validate a minimal payload."""
    DocumentModel.model_validate({"id": "x", "collection": "y"})
    CompletionResultModel.model_validate({"text": ""})
    LimitsResultModel.model_validate({})
    SubscriptionInfoModel.model_validate({})
    BalanceInfoModel.model_validate({})
    FileInfoModel.model_validate({"path": "x"})
    HTTPResponseModel.model_validate({"status_code": 200, "body": ""})
