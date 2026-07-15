"""Onboarding gate: `imperal init` scaffolds must build+validate CLEAN out of
the box — a fresh author must never hit a validation error before writing
code (5.9.5 fresh-app E2E found the tool template scaffolding a hyphenated
tool name that failed M5)."""
import os
import subprocess
import sys
import tempfile

import pytest

CLI = [sys.executable, "-m", "imperal_sdk.cli.main"]


@pytest.mark.parametrize("template", ["chat", "tool"])
def test_init_scaffold_builds_and_validates_clean(template):
    with tempfile.TemporaryDirectory() as tmp:
        # hyphenated app id = the M5 trap the template must survive
        app = os.path.join(tmp, "my-cool-app")
        r = subprocess.run(CLI + ["init", app, "--template", template],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        r = subprocess.run(CLI + ["build", app], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        r = subprocess.run(CLI + ["validate", app], capture_output=True, text=True)
        assert r.returncode == 0, (
            "a fresh `imperal init` scaffold must pass `imperal validate` "
            "with ZERO errors before the author writes any code:\n"
            + r.stdout + r.stderr
        )
