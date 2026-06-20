# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""F1: IR version stamps sourced from canonical constants / sdl_roles.json."""
import json
from pathlib import Path

import pytest

from imperal_sdk import Extension
from imperal_sdk.chat.extension import ChatExtension
from imperal_sdk.ir.produce import generate_ir
from imperal_sdk.ir.schema import IR_VERSION, CONTRACT_VERSION


@pytest.fixture()
def toy_ext():
    ext = Extension(app_id="toy_versions", version="1.0.0", display_name="Toy Versions")
    chat = ChatExtension(ext, description="Toy for version tests")

    @chat.function(name="ping", description="Ping")
    async def ping(ctx, params):  # pragma: no cover
        return None

    return ext


def test_versions_sourced_correctly(toy_ext):
    ir = generate_ir(toy_ext)
    assert ir["ir_version"] == IR_VERSION
    assert ir["contract_version"] == CONTRACT_VERSION
    # sdl_vocab_version must match the shipped sdl_roles.json
    roles_path = Path(__file__).resolve().parents[2] / "sdl_roles.json"
    roles = json.loads(roles_path.read_text())
    assert ir["sdl_vocab_version"] == roles["sdl_vocab_version"]
