from imperal_sdk.ir.validator import validate_ir_dict


def _valid():
    return {"ir_version": "1.0", "app": {"id": "a", "version": "1", "title": "A",
            "functions": [{"name": "f", "params_schema": {},
                           "impl": {"kind": "code", "module": "h", "entry": "fn"}}]}}


def test_valid_ir_has_no_issues():
    assert validate_ir_dict(_valid()) == []


def test_non_dict_root_reports_error():
    issues = validate_ir_dict(["not", "a", "dict"])
    assert any(i.level == "ERROR" for i in issues)


def test_bad_impl_kind_reports_error():
    bad = _valid()
    bad["app"]["functions"][0]["impl"] = {"kind": "nope"}
    issues = validate_ir_dict(bad)
    assert issues and all(i.level == "ERROR" for i in issues)


def test_missing_required_slot_reports_error():
    bad = _valid()
    del bad["app"]["id"]
    assert any(i.rule == "IR1" or i.level == "ERROR" for i in validate_ir_dict(bad))
