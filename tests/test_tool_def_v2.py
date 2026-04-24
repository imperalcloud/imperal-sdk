"""@ext.tool v2.0 contract: output_schema required, long_running/status_tool pair, description minimum."""
import pytest
from pydantic import BaseModel
from imperal_sdk import ext, Extension


class NoteResult(BaseModel):
    note_id: str
    created: bool


class StatusResult(BaseModel):
    done: bool


def test_tool_requires_output_schema():
    """v2 rejects @ext.tool without output_schema."""
    with pytest.raises(TypeError, match="output_schema"):
        class BrokenExt(Extension):
            @ext.tool(description="Creates a note in user's notebook")
            async def create_note(self, title: str) -> dict:
                return {"note_id": "x", "created": True}


def test_tool_requires_min_description_length():
    """v2 rejects description < 20 chars."""
    with pytest.raises(ValueError, match="description"):
        class BrokenExt(Extension):
            @ext.tool(description="short", output_schema=NoteResult)
            async def create_note(self, title: str) -> NoteResult:
                return NoteResult(note_id="x", created=True)


def test_tool_with_all_required_fields_ok():
    """Valid v2 tool declaration passes."""
    class GoodExt(Extension):
        @ext.tool(
            description="Create a new note with the given title in the user's primary notebook",
            output_schema=NoteResult,
        )
        async def create_note(self, title: str) -> NoteResult:
            return NoteResult(note_id="x", created=True)

    assert "create_note" in GoodExt._tools_registry


def test_long_running_requires_status_tool():
    """v2: long_running=True without status_tool is rejected at class-def time."""
    with pytest.raises(ValueError, match="status_tool"):
        class BrokenExt(Extension):
            @ext.tool(
                description="Run analysis — this is a long operation on the user's case",
                output_schema=NoteResult,
                long_running=True,
                estimated_duration_s=600,
                # missing status_tool
            )
            async def run_analysis(self, case_id: int) -> NoteResult:
                return NoteResult(note_id="task-x", created=True)


def test_long_running_status_tool_must_exist_in_extension():
    """Declared status_tool must point to an actual tool method on the same ext."""
    with pytest.raises(ValueError, match="status_tool"):
        class BrokenExt(Extension):
            @ext.tool(
                description="Run analysis — this is a long operation on the user's case",
                output_schema=NoteResult,
                long_running=True,
                estimated_duration_s=600,
                status_tool="nonexistent_status_probe",
            )
            async def run_analysis(self, case_id: int) -> NoteResult:
                return NoteResult(note_id="task-x", created=True)

        # Finalisation check runs when first instance is created
        BrokenExt()


def test_long_running_with_valid_status_tool_ok():
    class GoodExt(Extension):
        @ext.tool(
            description="Run analysis — this is a long operation on the user's case",
            output_schema=NoteResult,
            long_running=True,
            estimated_duration_s=600,
            status_tool="analysis_status",
        )
        async def run_analysis(self, case_id: int) -> NoteResult:
            return NoteResult(note_id="task-x", created=True)

        @ext.tool(
            description="Companion status probe for run_analysis long-running tool",
            output_schema=StatusResult,
        )
        async def analysis_status(self, task_id: str) -> StatusResult:
            return StatusResult(done=False)

    assert "run_analysis" in GoodExt._tools_registry
    assert "analysis_status" in GoodExt._tools_registry
    # Should not raise on instantiation
    GoodExt()


def test_llm_backed_flag_recorded():
    class LBExt(Extension):
        @ext.tool(
            description="AI-powered transformation of text content for the user",
            output_schema=NoteResult,
            llm_backed=True,
        )
        async def transform_text(self, text: str) -> NoteResult:
            return NoteResult(note_id="x", created=True)

    tool = LBExt._tools_registry["transform_text"]
    assert getattr(tool, "llm_backed", False) is True


def test_cost_credits_default_zero():
    class CExt(Extension):
        @ext.tool(
            description="Simple read operation with no cost attached",
            output_schema=NoteResult,
        )
        async def read(self) -> NoteResult:
            return NoteResult(note_id="x", created=True)

    tool = CExt._tools_registry["read"]
    assert getattr(tool, "cost_credits", 0) == 0
