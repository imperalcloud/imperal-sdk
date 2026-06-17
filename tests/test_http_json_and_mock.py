"""Regression tests: HTTPResponse.json() on JSON-array bodies + MockHTTP headers."""
import asyncio

from imperal_sdk.types.models import HTTPResponse
from imperal_sdk.testing.mock_context import MockHTTP


def test_json_returns_list_for_array_body():
    """An array endpoint (e.g. WP /wp/v2/posts) yields a list body — must not raise."""
    r = HTTPResponse(status_code=200, body=[{"id": 1}, {"id": 2}])
    assert r.json() == [{"id": 1}, {"id": 2}]


def test_json_dict_body():
    assert HTTPResponse(status_code=200, body={"a": 1}).json() == {"a": 1}


def test_json_parses_str_and_bytes():
    assert HTTPResponse(status_code=200, body="[1, 2]").json() == [1, 2]
    assert HTTPResponse(status_code=200, body=b'{"a": 1}').json() == {"a": 1}


def test_mockhttp_get_sets_response_headers():
    mh = MockHTTP()
    mh.mock_get("/wp/v2/posts", [{"id": 1}], status=200, headers={"X-WP-Total": "57"})
    resp = asyncio.run(mh.get("https://example.com/wp/v2/posts"))
    assert resp.status_code == 200
    assert resp.headers.get("X-WP-Total") == "57"
    assert resp.json() == [{"id": 1}]


def test_mockhttp_post_headers_default_empty():
    mh = MockHTTP()
    mh.mock_post("/x", {"ok": True})
    resp = asyncio.run(mh.post("https://example.com/x"))
    assert resp.headers == {}
    assert resp.json() == {"ok": True}
