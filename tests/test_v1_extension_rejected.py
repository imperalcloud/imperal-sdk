"""End-to-end: v1-style extensions fail SDK v2 validation at every layer."""
import pytest
from pathlib import Path
from pydantic import BaseModel
from imperal_sdk import Extension, ext
from imperal_sdk.validators.v14_no_chatext import run_v14


class Out(BaseModel):
    x: int


def test_v1_chatextension_import_rejected_at_class_def():
    """v1 code: `from imperal_sdk import ChatExtension` fails at import time."""
    with pytest.raises(ImportError):
        from imperal_sdk import ChatExtension  # noqa: F401


def test_v1_system_prompt_class_attr_rejected():
    with pytest.raises(TypeError, match="_system_prompt"):
        class LegacyExt(Extension):
            _system_prompt = "legacy"

            @ext.tool(description="Twenty character minimum description here", output_schema=Out)
            async def do(self): return Out(x=1)


def test_v1_tool_without_output_schema_rejected():
    with pytest.raises(TypeError, match="output_schema"):
        class LegacyExt(Extension):
            @ext.tool(description="Twenty character minimum description here")
            async def do(self): return {"x": 1}


def test_v1_short_description_rejected():
    with pytest.raises(ValueError, match="description"):
        class LegacyExt(Extension):
            @ext.tool(description="short", output_schema=Out)
            async def do(self): return Out(x=1)


def test_v14_detects_legacy_ext_in_dir(tmp_path):
    ext_dir = tmp_path / "legacy_ext"
    ext_dir.mkdir()
    (ext_dir / "main.py").write_text("""
from imperal_sdk import ChatExtension, ext

class Legacy(ChatExtension):
    _system_prompt = "I am a legacy assistant"
""")
    (ext_dir / "prompts").mkdir()
    (ext_dir / "prompts" / "system_prompt.txt").write_text("legacy")

    result = run_v14(ext_dir)
    assert not result.passed
    # Should catch all three v1 markers
    issues_joined = " ".join(result.issues)
    assert "ChatExtension" in issues_joined
    assert "_system_prompt" in issues_joined
    assert "system_prompt.txt" in issues_joined
