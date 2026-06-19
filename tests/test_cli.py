# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
import os
import pytest
from click.testing import CliRunner
from imperal_sdk import __version__
from imperal_sdk.cli.main import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output  # CLI reports the real SDK version


def test_cli_init_chat_template():
    """Default chat template generates v4-compliant ChatExtension + ActionResult scaffold."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "my-test-ext"])
        assert result.exit_code == 0
        assert "Extension 'my-test-ext' scaffolded" in result.output
        assert "(template: chat)" in result.output
        assert os.path.exists("my-test-ext/main.py")
        assert os.path.exists("my-test-ext/icon.svg")  # V21 federal — required
        assert os.path.exists("my-test-ext/requirements.txt")
        assert os.path.exists("my-test-ext/tests/test_main.py")
        assert os.path.exists("my-test-ext/.gitignore")

        with open("my-test-ext/main.py") as f:
            content = f.read()
            assert '"my-test-ext"' in content
            assert "ChatExtension" in content
            assert "ActionResult" in content
            assert 'version="1.0.0"' in content
            # v4 federal kwargs that v4.1.9 fix added
            assert "display_name=" in content
            assert "description=" in content
            assert "icon=" in content
            assert "actions_explicit=True" in content

        with open("my-test-ext/requirements.txt") as f:
            assert "imperal-sdk>=5.0.0" in f.read()  # scaffold pins current major

        with open("my-test-ext/icon.svg") as f:
            svg = f.read()
            assert "<svg" in svg
            assert "viewBox" in svg


def test_cli_init_tool_template():
    """Tool template generates bare @ext.tool scaffold (v4-compliant)."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "my-tool-ext", "--template", "tool"])
        assert result.exit_code == 0
        assert "(template: tool)" in result.output
        assert os.path.exists("my-tool-ext/main.py")
        assert os.path.exists("my-tool-ext/icon.svg")

        with open("my-tool-ext/main.py") as f:
            content = f.read()
            assert '"my-tool-ext"' in content
            assert "@ext.tool" in content
            assert 'version="1.0.0"' in content
            # v4 federal kwargs (added in v4.1.9 init scaffold fix)
            assert "display_name=" in content
            assert "actions_explicit=True" in content


def test_cli_init_invalid_template():
    """Unknown template value is rejected by Click."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "x", "--template", "invalid"])
        assert result.exit_code != 0
