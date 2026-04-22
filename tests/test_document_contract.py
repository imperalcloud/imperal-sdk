"""Contract test: Document dataclass and DocumentModel Pydantic must align.

Prevents the duplication drift that existed pre-1.5.25, where
``imperal_sdk.store.client.Document`` and ``imperal_sdk.types.models.Document``
were two separate dataclasses with diverging field sets and defaults.
Post-1.5.25 there is ONE canonical class in ``types.models`` and
``store.client`` re-exports it.
"""
from dataclasses import fields, asdict

from imperal_sdk.types.models import Document
from imperal_sdk.types.client_contracts import DocumentModel


def test_document_dataclass_fields_match_pydantic_model():
    """Every dataclass field must exist in Pydantic model (contract parity)."""
    dc_fields = {f.name for f in fields(Document)}
    pyd_fields = set(DocumentModel.model_fields.keys())
    missing_in_pydantic = dc_fields - pyd_fields
    assert not missing_in_pydantic, (
        f"Document dataclass has fields absent from DocumentModel: "
        f"{missing_in_pydantic}. Add them to DocumentModel or remove "
        f"from Document."
    )


def test_document_dataclass_roundtrip_through_pydantic():
    """Dataclass instance must validate cleanly through Pydantic model."""
    doc = Document(
        id="abc", collection="c", data={"x": 1},
        extension_id="ext", tenant_id="t", user_id="u1",
    )
    d = asdict(doc)
    validated = DocumentModel.model_validate(d)
    assert validated.id == "abc"
    assert validated.user_id == "u1"
    assert validated.extension_id == "ext"
    assert validated.tenant_id == "t"


def test_store_client_document_is_same_class():
    """store.client.Document is the canonical one from types.models."""
    from imperal_sdk.store.client import Document as ClientDoc
    from imperal_sdk.types.models import Document as CanonicalDoc
    assert ClientDoc is CanonicalDoc, (
        "Document must be a single class, not duplicated. "
        "store.client.Document should be imported from types.models."
    )


def test_top_level_document_is_same_class():
    """imperal_sdk.Document re-export resolves to the canonical class."""
    import imperal_sdk
    from imperal_sdk.types.models import Document as CanonicalDoc
    assert imperal_sdk.Document is CanonicalDoc


def test_document_has_helper_methods():
    """Helper methods __getitem__ and get() migrated from store.client."""
    doc = Document(id="a", collection="c", data={"k": "v"})
    assert doc["k"] == "v"
    assert doc.get("k") == "v"
    assert doc.get("missing") is None
    assert doc.get("missing", "fallback") == "fallback"


def test_document_default_values_match_pydantic():
    """Default values for the string fields must match DocumentModel defaults."""
    doc = Document(id="a", collection="c", data={})
    assert doc.extension_id == ""
    assert doc.tenant_id == "default"
    assert doc.created_at == ""
    assert doc.updated_at == ""
    assert doc.user_id == ""
