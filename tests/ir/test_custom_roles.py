from imperal_sdk.ir.custom_roles import validate_custom_roles


def test_app_owned_role_ok():
    assert validate_custom_roles([{"role": "ads.platform", "field": "platform"}]) == []


def test_reserved_namespace_rejected():
    issues = validate_custom_roles([{"role": "money.amount", "field": "amount"}])
    assert issues and issues[0].level == "ERROR"


def test_malformed_role_rejected():
    issues = validate_custom_roles([{"role": "NOTDOTTED", "field": "x"}])
    assert issues and issues[0].level == "ERROR"


def test_aggregates_multiple():
    issues = validate_custom_roles([
        {"role": "ads.platform", "field": "p"},   # ok
        {"role": "core.id", "field": "i"},         # reserved
        {"role": "bad role", "field": "b"},        # malformed
    ])
    assert len(issues) == 2
