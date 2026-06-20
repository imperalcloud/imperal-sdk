# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
from imperal_sdk.ir.produce import generate_ir
from imperal_sdk.ir.validator import validate_ir_dict
from imperal_sdk.chat.extension import ChatExtension
from imperal_sdk import Extension


def _toy_ext():
    # Real API: ChatExtension(ext, ...) auto-registers on ext._chat_extensions.
    # There is no add_chat_extension() method — construction is the registration.
    ext = Extension(app_id="toy", version="1.0.0", display_name="Toy")
    chat = ChatExtension(ext, description="Toy chat extension")

    @chat.function(name="ping", description="Ping")
    async def ping(ctx, params):  # pragma: no cover - body never called here
        return None

    return ext


def test_generate_ir_roundtrips_through_validator():
    ir = generate_ir(_toy_ext())
    assert ir["ir_version"] == "1.0"
    assert ir["app"]["id"] == "toy"
    fns = ir["app"]["functions"]
    assert any(f["name"] == "ping" for f in fns)
    assert all(f["impl"]["kind"] == "code" for f in fns)
    assert validate_ir_dict(ir) == []
