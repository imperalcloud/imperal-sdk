"""Tests for Imperal SDK error hierarchy."""
import pytest
from imperal_sdk.errors import (
    ImperalError, APIError, NotFoundError, RateLimitError,
    AuthError, ValidationError, ExtensionError, QuotaExceededError,
)


class TestImperalError:
    def test_base_error(self):
        err = ImperalError("something broke", code="test_error")
        assert str(err) == "something broke"
        assert err.message == "something broke"
        assert err.code == "test_error"

    def test_default_code(self):
        err = ImperalError("oops")
        assert err.code == "unknown"

    def test_is_exception(self):
        assert issubclass(ImperalError, Exception)


class TestAPIError:
    def test_api_error(self):
        err = APIError("server error", status_code=500)
        assert err.status_code == 500
        assert err.code == "api_error"
        assert isinstance(err, ImperalError)

    def test_custom_code(self):
        err = APIError("bad gateway", status_code=502, code="gateway_error")
        assert err.code == "gateway_error"


class TestNotFoundError:
    def test_not_found(self):
        err = NotFoundError("deal", "deal_123")
        assert err.resource == "deal"
        assert err.id == "deal_123"
        assert err.status_code == 404
        assert err.code == "not_found"
        assert "deal" in str(err)
        assert "deal_123" in str(err)

    def test_is_api_error(self):
        assert issubclass(NotFoundError, APIError)


class TestRateLimitError:
    def test_rate_limit(self):
        err = RateLimitError(retry_after=30)
        assert err.retry_after == 30
        assert err.status_code == 429
        assert err.code == "rate_limited"

    def test_default_retry(self):
        err = RateLimitError()
        assert err.retry_after == 60


class TestAuthError:
    def test_auth_error(self):
        err = AuthError()
        assert err.message == "Unauthorized"
        assert err.code == "auth_error"
        assert isinstance(err, ImperalError)

    def test_custom_message(self):
        err = AuthError("Token expired")
        assert err.message == "Token expired"


class TestValidationError:
    def test_validation(self):
        err = ValidationError("email", "must be valid email")
        assert err.field == "email"
        assert err.code == "validation_error"
        assert "email" in str(err)


class TestExtensionError:
    def test_extension_error(self):
        err = ExtensionError("crm", "function not found")
        assert err.app_id == "crm"
        assert err.code == "extension_error"
        assert "crm" in str(err)


class TestQuotaExceededError:
    def test_quota(self):
        err = QuotaExceededError("tokens", 50000)
        assert err.resource == "tokens"
        assert err.limit == 50000
        assert err.code == "quota_exceeded"


class TestErrorHierarchy:
    def test_catch_all_with_base(self):
        errors = [
            NotFoundError("x", "1"), RateLimitError(), AuthError(),
            ValidationError("f", "m"), ExtensionError("a", "m"), QuotaExceededError("r", 1),
        ]
        for err in errors:
            assert isinstance(err, ImperalError)

    def test_catch_api_errors(self):
        assert isinstance(NotFoundError("x", "1"), APIError)
        assert isinstance(RateLimitError(), APIError)
        assert not isinstance(AuthError(), APIError)
