import inspect
from dataclasses import fields
from imperal_sdk.chat.extension import FunctionDef, ChatExtension

def test_functiondef_event_schema_removed():
    names = {f.name for f in fields(FunctionDef)}
    assert "event_schema" not in names          # dead: never emitted/read
    # KEPT:
    assert "background" in names
    assert "long_running" in names
    assert "effects" in names
    assert "chain_callable" in names

def test_function_decorator_event_schema_removed():
    sig = inspect.signature(ChatExtension.function)
    assert "event_schema" not in sig.parameters
    assert "background" in sig.parameters
    assert "long_running" in sig.parameters
    assert "effects" in sig.parameters
    assert "data_model" in sig.parameters


def test_ctx_db_surface_removed():
    from imperal_sdk.context import Context
    from dataclasses import fields
    assert "db" not in {f.name for f in fields(Context)}
    import importlib, pytest
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("imperal_sdk.db")
    try:
        from imperal_sdk.context import DBProtocol  # noqa
        assert False, "DBProtocol should be removed"
    except ImportError:
        pass


def test_ctx_tools_surface_removed():
    from imperal_sdk.context import Context
    from dataclasses import fields
    assert "tools" not in {f.name for f in fields(Context)}
    import importlib, pytest
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("imperal_sdk.tools")
