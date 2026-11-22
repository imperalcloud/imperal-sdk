# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Federal-grade structured error taxonomy tests (P2 task 19).

Closes P0-4: raw exception strings bleeding into user-visible write args.
Every kernel-side error that surfaces in a tool_result / narration MUST
resolve through this catalog -> i18n key -> template rendering, not str(e).
"""


def test_taxonomy_exhaustive():
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY
    expected = {
        "VALIDATION_MISSING_FIELD", "VALIDATION_TYPE_ERROR", "FABRICATED_ID_SHAPE",
        "UNKNOWN_TOOL", "UNKNOWN_SUB_FUNCTION", "PERMISSION_DENIED",
        # K2: human-actionable auth / consent / billing codes
        "AUTH_EXPIRED", "MFA_REQUIRED", "CONSENT_REQUIRED", "PAYMENT_REQUIRED",
        "BACKEND_TIMEOUT", "BACKEND_5XX", "RATE_LIMITED", "INTERNAL",
        # 5.9.7: stamped by the kernel at the dispatch boundary when an
        # extension emits status="error" without a structured code
        # (I-EXT-ERROR-CODE-NORMALIZED).
        "EXT_UNSTRUCTURED_ERROR",
    }
    assert set(ERROR_TAXONOMY) == expected


def test_every_entry_has_i18n_key():
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY
    for code, entry in ERROR_TAXONOMY.items():
        assert "user_hint_i18n_key" in entry, f"{code} missing user_hint_i18n_key"
        assert entry["user_hint_i18n_key"].startswith("errors."), \
            f"{code} i18n key must be in errors.* namespace"


def test_default_en_and_ru_present():
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY
    for code, entry in ERROR_TAXONOMY.items():
        assert "default_en" in entry
        assert "default_ru" in entry
        # Non-empty strings.
        assert entry["default_en"].strip()
        assert entry["default_ru"].strip()


def test_known_error_codes_publicly_importable():
    from imperal_sdk.chat.error_codes import (
        VALIDATION_MISSING_FIELD, VALIDATION_TYPE_ERROR, FABRICATED_ID_SHAPE,
        UNKNOWN_TOOL, UNKNOWN_SUB_FUNCTION, PERMISSION_DENIED,
        AUTH_EXPIRED, MFA_REQUIRED, CONSENT_REQUIRED, PAYMENT_REQUIRED,
        BACKEND_TIMEOUT, BACKEND_5XX, RATE_LIMITED, INTERNAL,
        EXT_UNSTRUCTURED_ERROR,
    )
    assert VALIDATION_MISSING_FIELD == "VALIDATION_MISSING_FIELD"
    assert VALIDATION_TYPE_ERROR == "VALIDATION_TYPE_ERROR"
    assert FABRICATED_ID_SHAPE == "FABRICATED_ID_SHAPE"
    assert INTERNAL == "INTERNAL"
    assert UNKNOWN_TOOL == "UNKNOWN_TOOL"
    assert UNKNOWN_SUB_FUNCTION == "UNKNOWN_SUB_FUNCTION"
    assert PERMISSION_DENIED == "PERMISSION_DENIED"
    assert AUTH_EXPIRED == "AUTH_EXPIRED"
    assert MFA_REQUIRED == "MFA_REQUIRED"
    assert CONSENT_REQUIRED == "CONSENT_REQUIRED"
    assert PAYMENT_REQUIRED == "PAYMENT_REQUIRED"
    assert BACKEND_TIMEOUT == "BACKEND_TIMEOUT"
    assert BACKEND_5XX == "BACKEND_5XX"
    assert RATE_LIMITED == "RATE_LIMITED"
    assert EXT_UNSTRUCTURED_ERROR == "EXT_UNSTRUCTURED_ERROR"


def test_taxonomy_entries_are_frozen_shape():
    """Each entry is a dict with exactly the three known keys."""
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY
    allowed = {"user_hint_i18n_key", "default_en", "default_ru"}
    for code, entry in ERROR_TAXONOMY.items():
        assert set(entry.keys()) == allowed, \
            f"{code} has unexpected keys: {set(entry.keys()) - allowed}"


def test_i18n_keys_unique_per_code():
    """No two error codes share the same i18n key (would muddle UX + telemetry)."""
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY
    seen: dict[str, str] = {}
    for code, entry in ERROR_TAXONOMY.items():
        k = entry["user_hint_i18n_key"]
        assert k not in seen, \
            f"duplicate i18n key {k!r}: used by {seen[k]} and {code}"
        seen[k] = code


def test_default_ru_not_equal_to_default_en():
    """Sanity: a machine-copied catalog where RU == EN indicates a bug
    (accidental English leaking into Russian locale). Short generic strings
    ('INTERNAL') still have translated words."""
    from imperal_sdk.chat.error_codes import ERROR_TAXONOMY
    for code, entry in ERROR_TAXONOMY.items():
        assert entry["default_en"] != entry["default_ru"], \
            f"{code}: default_en and default_ru are byte-identical"


def test_human_action_error_codes_contract():
    from imperal_sdk.chat.error_codes import (
        ERROR_TAXONOMY,
        HUMAN_ACTION_ERROR_CODES,
        default_needs_human_for_code,
    )
    assert HUMAN_ACTION_ERROR_CODES == {
        "PERMISSION_DENIED": "means",
        "AUTH_EXPIRED": "means",
        "MFA_REQUIRED": "means",
        "CONSENT_REQUIRED": "decision",
        "PAYMENT_REQUIRED": "decision",
    }
    assert set(HUMAN_ACTION_ERROR_CODES).issubset(set(ERROR_TAXONOMY))
    for code, kind in HUMAN_ACTION_ERROR_CODES.items():
        assert default_needs_human_for_code(code, "Reconnect account") == {
            "what": "Reconnect account",
            "kind": kind,
        }
        fallback = default_needs_human_for_code(code, "   ")
        assert fallback == {
            "what": ERROR_TAXONOMY[code]["default_en"],
            "kind": kind,
        }
    for non_human in (
        "VALIDATION_MISSING_FIELD",
        "VALIDATION_TYPE_ERROR",
        "FABRICATED_ID_SHAPE",
        "UNKNOWN_TOOL",
        "UNKNOWN_SUB_FUNCTION",
        "BACKEND_TIMEOUT",
        "BACKEND_5XX",
        "RATE_LIMITED",
        "INTERNAL",
        "EXT_UNSTRUCTURED_ERROR",
        "CUSTOM_APP_ERROR",
        "",
    ):
        assert default_needs_human_for_code(non_human, "details") is None
