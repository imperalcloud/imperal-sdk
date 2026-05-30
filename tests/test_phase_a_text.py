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
