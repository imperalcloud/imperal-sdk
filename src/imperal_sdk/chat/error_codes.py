# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Structured error taxonomy (P2 task 19 — Federal-Grade Chat Integrity).

Purpose
-------
Replace ad-hoc ``str(exception)`` content that historically leaked into
user-visible writes (email bodies, note titles, SMS). Every kernel- or
SDK-side error that surfaces to an LLM tool_result MUST map to one of the
10 codes below; the corresponding i18n key drives the actual user-facing
copy via the platform's canonical response templates.

This module is *read-only data* — no logic, no fabrication surface.
Mirror at the platform narration mirror is kept byte-for-byte
compatible (enforced by ``scripts/validate_error_taxonomy.py`` in the
kernel).

Closes P0-4 ("raw exception strings bleeding into write-side tool args").

Invariants
----------
* Every entry has exactly ``user_hint_i18n_key`` + ``default_en`` + ``default_ru``.
* Every ``user_hint_i18n_key`` lives in the ``errors.*`` namespace.
* Defaults are generic (no PII, no host paths, no user tokens).
* SDK/kernel catalogs MUST match — enforced by
  ``test_sdk_kernel_catalogs_match`` in the kernel validator.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Public string constants (for ``from ... import VALIDATION_MISSING_FIELD``). #
# Values are equal to the dict keys — importers can pass either safely.       #
# --------------------------------------------------------------------------- #
VALIDATION_MISSING_FIELD = "VALIDATION_MISSING_FIELD"
VALIDATION_TYPE_ERROR = "VALIDATION_TYPE_ERROR"
FABRICATED_ID_SHAPE = "FABRICATED_ID_SHAPE"
UNKNOWN_TOOL = "UNKNOWN_TOOL"
UNKNOWN_SUB_FUNCTION = "UNKNOWN_SUB_FUNCTION"
PERMISSION_DENIED = "PERMISSION_DENIED"
AUTH_EXPIRED = "AUTH_EXPIRED"
MFA_REQUIRED = "MFA_REQUIRED"
CONSENT_REQUIRED = "CONSENT_REQUIRED"
PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
BACKEND_5XX = "BACKEND_5XX"
RATE_LIMITED = "RATE_LIMITED"
INTERNAL = "INTERNAL"
EXT_UNSTRUCTURED_ERROR = "EXT_UNSTRUCTURED_ERROR"


ERROR_TAXONOMY: dict[str, dict[str, str]] = {
    "VALIDATION_MISSING_FIELD": {
        "user_hint_i18n_key": "errors.validation.missing_field",
        "default_en": "A required field is missing: {fields}",
        "default_ru": "Отсутствует обязательное поле: {fields}",
    },
    "VALIDATION_TYPE_ERROR": {
        "user_hint_i18n_key": "errors.validation.type_error",
        "default_en": "Invalid value type for field: {field}",
        "default_ru": "Неверный тип значения для поля: {field}",
    },
    "FABRICATED_ID_SHAPE": {
        "user_hint_i18n_key": "errors.validation.fabricated_id_shape",
        "default_en": "The supplied id matches a known fabrication pattern; call inbox()/search()/folder() first to obtain a real id",
        "default_ru": "Идентификатор похож на сфабрикованный; сначала вызовите inbox()/search()/folder() и возьмите реальный id",
    },
    "UNKNOWN_TOOL": {
        "user_hint_i18n_key": "errors.dispatch.unknown_tool",
        "default_en": "Tool not available: {app_tool}",
        "default_ru": "Инструмент недоступен: {app_tool}",
    },
    "UNKNOWN_SUB_FUNCTION": {
        "user_hint_i18n_key": "errors.dispatch.unknown_sub_function",
        "default_en": "Sub-function not available: {name}",
        "default_ru": "Функция не найдена: {name}",
    },
    "PERMISSION_DENIED": {
        "user_hint_i18n_key": "errors.auth.permission_denied",
        "default_en": "Permission denied for this action",
        "default_ru": "Нет прав на это действие",
    },
    "AUTH_EXPIRED": {
        "user_hint_i18n_key": "errors.auth.expired",
        "default_en": "Authentication has expired; please reconnect the account",
        "default_ru": "Авторизация истекла; переподключите аккаунт",
    },
    "MFA_REQUIRED": {
        "user_hint_i18n_key": "errors.auth.mfa_required",
        "default_en": "Multi-factor verification is required to continue",
        "default_ru": "Для продолжения требуется двухфакторная проверка",
    },
    "CONSENT_REQUIRED": {
        "user_hint_i18n_key": "errors.auth.consent_required",
        "default_en": "Explicit approval is required before performing this action",
        "default_ru": "Для выполнения этого действия требуется явное подтверждение",
    },
    "PAYMENT_REQUIRED": {
        "user_hint_i18n_key": "errors.billing.payment_required",
        "default_en": "Payment or plan upgrade is required to continue",
        "default_ru": "Для продолжения требуется оплата или обновление тарифа",
    },
    "BACKEND_TIMEOUT": {
        "user_hint_i18n_key": "errors.backend.timeout",
        "default_en": "The backend service timed out; please retry",
        "default_ru": "Бэкенд не ответил вовремя; попробуйте ещё раз",
    },
    "BACKEND_5XX": {
        "user_hint_i18n_key": "errors.backend.5xx",
        "default_en": "The backend service returned an error; please retry",
        "default_ru": "Бэкенд вернул ошибку; попробуйте ещё раз",
    },
    "RATE_LIMITED": {
        "user_hint_i18n_key": "errors.rate_limited",
        "default_en": "Too many requests; please slow down",
        "default_ru": "Слишком много запросов; попробуйте позже",
    },
    "INTERNAL": {
        "user_hint_i18n_key": "errors.internal",
        "default_en": "An internal error occurred",
        "default_ru": "Внутренняя ошибка",
    },
    # Attached by the KERNEL at the dispatch boundary when an extension emits
    # status="error" WITHOUT a structured code (I-EXT-ERROR-CODE-NORMALIZED):
    # the narrator always gets a stable code FACT even for extensions that
    # only ship prose. Extensions should pass ActionResult.error(code=...)
    # instead — validator rule V32 flags code-less error call sites.
    "EXT_UNSTRUCTURED_ERROR": {
        "user_hint_i18n_key": "errors.ext.unstructured",
        "default_en": "The app reported an error without a structured code",
        "default_ru": "Приложение сообщило об ошибке без структурного кода",
    },
}


# Error codes that ONLY the human can resolve — auto-marked as ``needs_human``
# by ActionResult when emitted. Every other code (validation, transient backend
# errors, unknown tool, EXT_UNSTRUCTURED_ERROR) is NOT auto-marked here: the
# model, retries, or the platform handles them without guessing from prose.
HUMAN_ACTION_ERROR_CODES: dict[str, str] = {
    PERMISSION_DENIED: "means",
    AUTH_EXPIRED: "means",
    MFA_REQUIRED: "means",
    CONSENT_REQUIRED: "decision",
    PAYMENT_REQUIRED: "decision",
}


# Maximum length of ``needs_human["what"]`` derived from extension error text.
NEEDS_HUMAN_WHAT_LIMIT = 500


def default_needs_human_for_code(
    code: str,
    message: str = "",
) -> dict[str, str] | None:
    """Return ``{"what": ..., "kind": ...}`` if ``code`` requires human action.

    Returns ``None`` for codes that do not require human intervention.
    Extension error text is bounded with ``imperal_sdk.evidence.cut_text``.
    """
    kind = HUMAN_ACTION_ERROR_CODES.get(code)
    if kind is None:
        return None
    what = (message or "").strip()
    if not what:
        entry = ERROR_TAXONOMY.get(code)
        what = (entry.get("default_en") if entry else None) or code
    else:
        from imperal_sdk.evidence import cut_text

        what, _ = cut_text(what, NEEDS_HUMAN_WHAT_LIMIT)
    return {"what": what, "kind": kind}


__all__ = [
    "ERROR_TAXONOMY",
    "HUMAN_ACTION_ERROR_CODES",
    "NEEDS_HUMAN_WHAT_LIMIT",
    "default_needs_human_for_code",
    "VALIDATION_MISSING_FIELD",
    "VALIDATION_TYPE_ERROR",
    "FABRICATED_ID_SHAPE",
    "UNKNOWN_TOOL",
    "UNKNOWN_SUB_FUNCTION",
    "PERMISSION_DENIED",
    "AUTH_EXPIRED",
    "MFA_REQUIRED",
    "CONSENT_REQUIRED",
    "PAYMENT_REQUIRED",
    "BACKEND_TIMEOUT",
    "BACKEND_5XX",
    "RATE_LIMITED",
    "INTERNAL",
    "EXT_UNSTRUCTURED_ERROR",
]
