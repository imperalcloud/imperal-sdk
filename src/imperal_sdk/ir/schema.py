from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IRApp(BaseModel):
    """The app body of an IR envelope (everything an app declares)."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    version: str
    title: str
    description: str = ""
    icon: str = ""
    capabilities: list[str] = Field(default_factory=list)

    # Slots — typed in later tasks; opaque for now so a minimal app validates.
    data: dict[str, Any] | None = None
    functions: list[dict[str, Any]] = Field(default_factory=list)
    ui: dict[str, Any] | None = None
    skeleton: dict[str, Any] | None = None
    automations: list[dict[str, Any]] = Field(default_factory=list)
    events: dict[str, Any] | None = None
    lifecycle: dict[str, Any] | None = None


class IREnvelope(BaseModel):
    """Versioned root of the Imperal IR."""
    model_config = ConfigDict(extra="forbid")

    ir_version: str
    sdl_vocab_version: str = "1"
    contract_version: str = "1.0"
    app: IRApp


def get_ir_schema() -> dict[str, Any]:  # filled out in Task A3
    schema = IREnvelope.model_json_schema()
    schema["$id"] = "https://imperal.io/schemas/ir.schema.json"
    schema["title"] = "Imperal IR Envelope"
    return schema
