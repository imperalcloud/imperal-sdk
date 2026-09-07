import pytest
from imperal_sdk.extension import Extension
from imperal_sdk.search import SearchEntityResult, SearchProviderDef


def test_search_entity_result_serialization():
    res = SearchEntityResult(
        id="cust_982",
        title="John Doe (Enterprise)",
        type="customer",
        snippet="Customer requested custom invoice billing for Q3",
        score=0.94,
        url="/workspace/billing?customer=cust_982",
        metadata={"plan": "enterprise", "country": "DE"},
    )
    d = res.to_dict()
    assert d["id"] == "cust_982"
    assert d["title"] == "John Doe (Enterprise)"
    assert d["type"] == "customer"
    assert d["score"] == 0.94
    assert d["url"] == "/workspace/billing?customer=cust_982"
    assert d["metadata"]["country"] == "DE"


def test_extension_search_provider_registration():
    ext = Extension("test-omnisearch")

    @ext.search_provider("customers", description="Search CRM customer records")
    def find_customers(query: str):
        return [
            SearchEntityResult(id="1", title="Alice", type="customer"),
        ]

    assert "customers" in ext._search_providers
    p_def = ext._search_providers["customers"]
    assert isinstance(p_def, SearchProviderDef)
    assert p_def.entity_type == "customers"
    assert p_def.description == "Search CRM customer records"
    assert p_def.to_manifest() == {
        "entity_type": "customers",
        "handler": "find_customers",
        "description": "Search CRM customer records",
    }


def test_manifest_search_providers_validate_roundtrip():
    from imperal_sdk.manifest import generate_manifest, validate_manifest_dict

    ext = Extension("test-omnisearch")

    @ext.search_provider("customers", description="Search CRM customer records")
    def find_customers(query: str):
        return []

    manifest = generate_manifest(ext)
    assert "search_providers" in manifest
    assert len(manifest["search_providers"]) == 1
    assert manifest["search_providers"][0]["entity_type"] == "customers"
    assert manifest["search_providers"][0]["handler"] == "find_customers"

    issues = validate_manifest_dict(manifest)
    assert issues == [], f"Expected clean validation but got: {issues}"
