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
    def test_is_valid_no_errors(self):
        ext = Extension("crm", version="1.0.0")

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        assert report.is_valid is True

    def test_is_valid_with_errors(self):
        ext = Extension("", version="bad")
        report = validate_extension(ext)
        assert report.is_valid is False
        assert len(report.errors) >= 2

    def test_report_counts(self):
        ext = Extension("crm", version="1.0.0")

        @ext.tool("test")
        async def test(ctx):
            pass

        report = validate_extension(ext)
        assert report.app_id == "crm"
        assert report.version == "1.0.0"
        assert report.tool_count == 1
