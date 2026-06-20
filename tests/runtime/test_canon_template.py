import pytest
from imperal_sdk.runtime.canon import project_canon, CanonError


def test_kind_const():
    assert project_canon({"kind_const": "campaign"}, {})["kind"] == "campaign"


def test_title_template_substitution_and_count_filter():
    spec = {"title_template": "{{name}} — {{count(adsets)}} ad sets"}
    out = project_canon(spec, {"name": "Promo", "adsets": [1, 2, 3]})
    assert out["title"] == "Promo — 3 ad sets"


def test_title_template_default_filter():
    spec = {"title_template": "{{name | default:'Untitled'}}"}
    assert project_canon(spec, {})["title"] == "Untitled"


def test_unlisted_filter_raises():
    with pytest.raises(CanonError):
        project_canon({"title_template": "{{name | eval}}"}, {"name": "x"})
