"""v2.0: Extension subclass with _system_prompt attribute is rejected."""
import pytest
from imperal_sdk import Extension, ext
from pydantic import BaseModel


class DummyOutput(BaseModel):
    x: int


def test_system_prompt_as_class_attr_rejected():
    with pytest.raises(TypeError, match="_system_prompt"):
        class LegacyExt(Extension):
            _system_prompt = "I am the legacy assistant"

            @ext.tool(description="Dummy tool with long-enough description text", output_schema=DummyOutput)
            async def do(self) -> DummyOutput:
                return DummyOutput(x=1)


def test_system_prompt_as_instance_attr_rejected():
    """Even if set in __init__, Extension must reject _system_prompt."""
    class LegacyExt(Extension):
        def __init__(self):
            super().__init__()
            self._system_prompt = "I am the legacy assistant"

        @ext.tool(description="Dummy tool with long-enough description text", output_schema=DummyOutput)
        async def do(self) -> DummyOutput:
            return DummyOutput(x=1)

    with pytest.raises(TypeError, match="_system_prompt"):
        LegacyExt()


def test_clean_extension_passes():
    class CleanExt(Extension):
        @ext.tool(description="Dummy tool with long-enough description text", output_schema=DummyOutput)
        async def do(self) -> DummyOutput:
            return DummyOutput(x=1)

    ext_instance = CleanExt()
    assert ext_instance is not None
    assert not hasattr(ext_instance, "_system_prompt")
