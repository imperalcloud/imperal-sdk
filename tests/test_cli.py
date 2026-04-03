# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import os
import shutil
import pytest
from click.testing import CliRunner
from imperal_sdk.cli.main import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.output


def test_cli_init():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["init", "my-test-ext"])
        assert result.exit_code == 0
        assert "Extension 'my-test-ext' created!" in result.output
        assert os.path.exists("my-test-ext/main.py")
        assert os.path.exists("my-test-ext/requirements.txt")
        assert os.path.exists("my-test-ext/tests/test_hello.py")
        assert os.path.exists("my-test-ext/.gitignore")

        with open("my-test-ext/main.py") as f:
            content = f.read()
            assert 'Extension("my-test-ext"' in content
            assert '@ext.tool("hello"' in content
