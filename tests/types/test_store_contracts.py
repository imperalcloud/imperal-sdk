"""Contract tests for store.list_users wire format."""
import pytest
from pydantic import ValidationError

from imperal_sdk.types.store_contracts import ListUsersRequest, ListUsersResponse


def test_request_happy_path():
    req = ListUsersRequest(collection="wt_monitors", extension_id="web-tools",
                           tenant_id="default")
    assert req.limit == 500


def test_request_limit_bounds():
    with pytest.raises(ValidationError):
        ListUsersRequest(collection="c", extension_id="e", tenant_id="t", limit=0)
    with pytest.raises(ValidationError):
        ListUsersRequest(collection="c", extension_id="e", tenant_id="t", limit=100000)


def test_response_roundtrip_json():
    resp = ListUsersResponse(user_ids=["u1", "u2"], next_cursor="500", truncated=False)
    assert ListUsersResponse.model_validate_json(resp.model_dump_json()) == resp


def test_response_empty():
    resp = ListUsersResponse(user_ids=[], next_cursor=None, truncated=False)
    assert resp.user_ids == []


def test_module_docstring_declares_single_source():
    import imperal_sdk.types.store_contracts as mod
    assert "I-SDK-GW-CONTRACT-1" in mod.__doc__
