from imperal_sdk.chat.extension import FunctionDef, ChatExtension


def test_effects_docstring_is_advisory():
    doc = (FunctionDef.__doc__ or "") + (ChatExtension.function.__doc__ or "")
    assert "advisory" in doc.lower() or "not currently consume" in doc.lower()
    # the old false claim that the kernel narrator/audit-ledger consumes effects must be gone:
    assert "can describe exactly what changed" not in doc


def test_background_long_running_docstring_is_advisory():
    # The function() Args block must independently mark background AND
    # long_running as advisory (not just effects).
    fn_doc = (ChatExtension.function.__doc__ or "").lower()
    assert "background" in fn_doc and "long_running" in fn_doc
    assert "advisory" in fn_doc or "does not consume" in fn_doc


def test_validator_effects_message_not_a_consumption_claim():
    # The V20 effects validator must not claim the kernel consumes effects.
    import imperal_sdk.validator as v
    src = open(v.__file__, encoding="utf-8").read()
    assert "Used by chain narrator + audit ledger" not in src
    assert "Effects power the audit ledger" not in src


def test_data_model_docstring_no_emit_validate_claim():
    doc = ChatExtension.function.__doc__ or ""
    assert "Runtime ``data.model_validate`` on emit" not in doc


def test_api_surface_no_skeleton_update_no_db():
    # Source of truth is the live surface, not a frozen file (the stale SDK-root
    # api_surface.json was deleted in Ф1; the docs_guard copy is freshness-tested).
    from imperal_sdk.devtools.generate_api_surface import generate_surface
    s = generate_surface()
    assert "update" not in s.get("skeleton", [])   # SkeletonClient read-only since v1.6.0
    assert "db" not in s                            # ctx.db removed in Phase A
    assert s.get("skeleton") == ["get"]             # the only skeleton method


def test_chain_callable_docstring_unconditional_true():
    doc = FunctionDef.__doc__ or ""
    before_id_projection = doc.split("id_projection")[0]
    # no "True for any action_type other than read" lie:
    assert "other than" not in before_id_projection
    # positive: states the unconditional/all-action-types default:
    assert "v4.2.10" in before_id_projection


def test_validate_manifest_dict_docstring_states_it_raises():
    import imperal_sdk.manifest_schema as ms
    doc = ms.validate_manifest_dict.__doc__ or ""
    assert "non-raising" not in doc.lower()
    assert "raise" in doc.lower()
    # the module-level summary must also stop calling it non-raising:
    assert "(non-raising)" not in (ms.__doc__ or "")


def test_sdk_version_floor_is_5_0_0():
    from imperal_sdk.validator_v1_6_0 import validate_manifest_v1_6_0
    # sub-5.0.0 is loader-fatal -> ERROR
    sub = validate_manifest_v1_6_0(
        {"app_id": "x", "version": "1.0.0", "sdk_version": "4.2.0"})
    sdkv = [i for i in sub if i.rule == "SDK-VERSION-1"]
    assert sdkv and all(i.level == "ERROR" for i in sdkv)
    # missing sdk_version -> ERROR
    missing = validate_manifest_v1_6_0({"app_id": "x", "version": "1.0.0"})
    assert any(i.rule == "SDK-VERSION-1" and i.level == "ERROR" for i in missing)
    # 5.0.0 (the exact floor) and any newer version pass clean
    for good in ("5.0.0", "5.0.1", "5.1.0"):
        ok = validate_manifest_v1_6_0(
            {"app_id": "x", "version": "1.0.0", "sdk_version": good})
        assert not [i for i in ok if i.rule == "SDK-VERSION-1"]
