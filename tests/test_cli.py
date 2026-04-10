# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import os
import pytest
from click.testing import CliRunner
from imperal_sdk.cli.main import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.4.1" in result.output


def test_cli_init_chat_template():
    """Default chat template generates ChatExtension + ActionResult scaffold."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "my-test-ext"])
        assert result.exit_code == 0
        assert "Extension 'my-test-ext' created!" in result.output
        assert "(template: chat)" in result.output
        assert os.path.exists("my-test-ext/main.py")
        assert os.path.exists("my-test-ext/requirements.txt")
        assert os.path.exists("my-test-ext/tests/test_main.py")
        assert os.path.exists("my-test-ext/.gitignore")

        with open("my-test-ext/main.py") as f:
            content = f.read()
            assert 'Extension("my-test-ext"' in content
            assert "ChatExtension" in content
            assert "ActionResult" in content
            assert 'version="1.0.0"' in content

        with open("my-test-ext/requirements.txt") as f:
            assert "imperal-sdk>=1.0.0" in f.read()


def test_cli_init_tool_template():
    """Tool template generates bare @ext.tool scaffold."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "my-tool-ext", "--template", "tool"])
        assert result.exit_code == 0
        assert "(template: tool)" in result.output
        assert os.path.exists("my-tool-ext/main.py")

        with open("my-tool-ext/main.py") as f:
            content = f.read()
            assert 'Extension("my-tool-ext"' in content
            assert "@ext.tool" in content
            assert 'version="1.0.0"' in content


def test_cli_init_invalid_template():
    """Unknown template value is rejected by Click."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "x", "--template", "invalid"])
        assert result.exit_code != 0
