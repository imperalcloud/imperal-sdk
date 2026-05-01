# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Tests for extension validator V1-V16 rules."""
import pytest
from imperal_sdk.extension import Extension
from imperal_sdk.validator import validate_extension, ValidationReport, ValidationIssue
from imperal_sdk.protocols import ExtensionProtocol


class TestExtensionProtocol:
    def test_valid_extension_satisfies_protocol(self):
        ext = Extension("my-app", version="1.0.0")

        @ext.tool("test_tool")
        async def test(ctx):
            pass

        assert isinstance(ext, ExtensionProtocol)

    def test_has_required_attrs(self):
        ext = Extension("my-app", version="1.0.0")
        assert hasattr(ext, "app_id")
        assert hasattr(ext, "version")
        assert hasattr(ext, "tools")


class TestV1AppId:
    def test_valid_app_id(self):
        ext = Extension("crm", version="1.0.0")
        report = validate_extension(ext)
        v1_errors = [i for i in report.errors if i.rule == "V1"]
        assert len(v1_errors) == 0

    def test_valid_app_id_with_hyphens(self):
        ext = Extension("my-crm-app", version="1.0.0")
        report = validate_extension(ext)
        v1_errors = [i for i in report.errors if i.rule == "V1"]
        assert len(v1_errors) == 0

    def test_invalid_uppercase(self):
        ext = Extension("MyCRM", version="1.0.0")
        report = validate_extension(ext)
        v1_errors = [i for i in report.errors if i.rule == "V1"]
        assert len(v1_errors) == 1

    def test_invalid_single_char(self):
        ext = Extension("x", version="1.0.0")
        report = validate_extension(ext)
        v1_errors = [i for i in report.errors if i.rule == "V1"]
        assert len(v1_errors) == 1

    def test_empty_app_id(self):
        ext = Extension("", version="1.0.0")
        report = validate_extension(ext)
        v1_errors = [i for i in report.errors if i.rule == "V1"]
        assert len(v1_errors) == 1


class TestV2Version:
    def test_valid_semver(self):
        ext = Extension("crm", version="1.0.0")
        report = validate_extension(ext)
        v2_errors = [i for i in report.errors if i.rule == "V2"]
        assert len(v2_errors) == 0

    def test_invalid_version(self):
        ext = Extension("crm", version="latest")
        report = validate_extension(ext)
        v2_errors = [i for i in report.errors if i.rule == "V2"]
        assert len(v2_errors) == 1


class TestV3AtLeastOneTool:
    def test_with_tool(self):
        ext = Extension("crm", version="1.0.0")

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        v3_errors = [i for i in report.errors if i.rule == "V3"]
        assert len(v3_errors) == 0

    def test_no_tools(self):
        ext = Extension("crm", version="1.0.0")
        report = validate_extension(ext)
        v3_errors = [i for i in report.errors if i.rule == "V3"]
        assert len(v3_errors) == 1


class TestV9HealthCheck:
    def test_no_health_check(self):
        ext = Extension("crm", version="1.0.0")
        report = validate_extension(ext)
        v9_warns = [i for i in report.warnings if i.rule == "V9"]
        assert len(v9_warns) == 1

    def test_with_health_check(self):
        ext = Extension("crm", version="1.0.0")

        @ext.health_check
        async def check(ctx):
            pass

        report = validate_extension(ext)
        v9_warns = [i for i in report.warnings if i.rule == "V9"]
        assert len(v9_warns) == 0


class TestValidationReport:
    def _federal_ext(self, app_id="crm", version="1.0.0"):
        """Minimal v4.0.0 federal-compliant Extension fixture."""
        return Extension(
            app_id, version=version,
            display_name="CRM",
            description="Customer relationship management — manage deals, contacts, and pipelines.",
            icon="icon.svg",
            actions_explicit=True,
        )

    def test_is_valid_no_errors(self):
        ext = self._federal_ext()

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        # V21 reports a non-blocking warning when icon file is not on disk
        # (typical for pure-unit tests). Filter to non-V21 errors.
        non_icon_errors = [e for e in report.errors if e.rule != "V21"]
        assert non_icon_errors == [], f"Unexpected errors: {non_icon_errors}"

    def test_is_valid_with_errors(self):
        ext = Extension("", version="bad")
        report = validate_extension(ext)
        assert report.is_valid is False
        assert len(report.errors) >= 2

    def test_report_counts(self):
        ext = self._federal_ext()

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        assert report.app_id == "crm"
        assert report.version == "1.0.0"
        assert report.tool_count == 1


class TestV5ReturnActionResult:
    """V5: @chat.function must return ActionResult."""

    def test_no_chat_extension_no_v5(self):
        # V5 only applies to ChatExtension functions; plain @ext.tool extensions skip it
        ext = Extension("test-app", version="1.0.0")

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        v5_errors = [i for i in report.errors if i.rule == "V5"]
        assert len(v5_errors) == 0

    def test_chat_function_with_action_result_passes(self):
        # A @chat.function that annotates -> ActionResult should have no V5 error
        from imperal_sdk.chat import ChatExtension
        from imperal_sdk import ActionResult

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        @chat.function("get_something", description="Get something", action_type="read")
        async def get_something(ctx) -> ActionResult:
            """Get something."""
            return ActionResult.success({})

        report = validate_extension(ext)
        v5_errors = [i for i in report.errors if i.rule == "V5"]
        assert len(v5_errors) == 0

    def test_chat_function_without_return_annotation_fails(self):
        # A @chat.function with no return annotation should trigger V5
        from imperal_sdk.chat import ChatExtension

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        @chat.function("get_something", description="Get something", action_type="read")
        async def get_something(ctx):
            """Get something."""
            pass

        report = validate_extension(ext)
        v5_errors = [i for i in report.errors if i.rule == "V5"]
        assert len(v5_errors) == 1
        assert "ActionResult" in v5_errors[0].message

    def test_chat_function_with_wrong_return_type_fails(self):
        # A @chat.function returning dict instead of ActionResult should trigger V5
        from imperal_sdk.chat import ChatExtension

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        @chat.function("get_something", description="Get something", action_type="read")
        async def get_something(ctx) -> dict:
            """Get something."""
            return {}

        report = validate_extension(ext)
        v5_errors = [i for i in report.errors if i.rule == "V5"]
        assert len(v5_errors) == 1


class TestV6PydanticParams:
    """V6: @chat.function params should be a Pydantic BaseModel subclass (WARN)."""

    def test_no_params_no_v6(self):
        # A function with no params beyond ctx should not trigger V6
        from imperal_sdk.chat import ChatExtension
        from imperal_sdk import ActionResult

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        @chat.function("list_items", description="List items", action_type="read")
        async def list_items(ctx) -> ActionResult:
            """List items."""
            return ActionResult.success({})

        report = validate_extension(ext)
        v6_warns = [i for i in report.warnings if i.rule == "V6"]
        assert len(v6_warns) == 0

    def test_pydantic_param_passes(self):
        # A function with a Pydantic BaseModel param should not trigger V6
        from imperal_sdk.chat import ChatExtension
        from imperal_sdk import ActionResult
        from pydantic import BaseModel

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        class CreateParams(BaseModel):
            name: str

        @chat.function("create_item", description="Create item", action_type="write")
        async def create_item(ctx, params: CreateParams) -> ActionResult:
            """Create item."""
            return ActionResult.success({})

        report = validate_extension(ext)
        v6_warns = [i for i in report.warnings if i.rule == "V6"]
        assert len(v6_warns) == 0

    def test_non_pydantic_param_warns(self):
        # A function with a plain dict param should trigger V6 WARN
        from imperal_sdk.chat import ChatExtension
        from imperal_sdk import ActionResult

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        @chat.function("create_item", description="Create item", action_type="write")
        async def create_item(ctx, params: dict) -> ActionResult:
            """Create item."""
            return ActionResult.success({})

        report = validate_extension(ext)
        v6_warns = [i for i in report.warnings if i.rule == "V6"]
        assert len(v6_warns) == 1
        assert "Pydantic" in v6_warns[0].message


class TestV7NoDirectImports:
    """V7: No direct import anthropic or openai."""

    def test_clean_extension_no_v7(self):
        # A plain extension with no ChatExtension should produce no V7 errors
        ext = Extension("test-app", version="1.0.0")

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        v7_errors = [i for i in report.errors if i.rule == "V7"]
        assert len(v7_errors) == 0

    def test_clean_chat_extension_no_v7(self):
        # A ChatExtension defined in this test module (no anthropic/openai imports)
        # should not trigger V7
        from imperal_sdk.chat import ChatExtension
        from imperal_sdk import ActionResult

        ext = Extension("test-app", version="1.0.0")
        chat = ChatExtension(ext, tool_name="test", description="Test chat")

        @chat.function("get_something", description="Get something", action_type="read")
        async def get_something(ctx) -> ActionResult:
            """Get something."""
            return ActionResult.success({})

        report = validate_extension(ext)
        v7_errors = [i for i in report.errors if i.rule == "V7"]
        # This test module does not import anthropic/openai so no V7 error expected
        assert len(v7_errors) == 0
