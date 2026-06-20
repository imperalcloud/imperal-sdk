from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .ui import IRPanel


class ImplCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["code"]
    module: str
    entry: str


class ImplDeclarative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["declarative"]
    steps: list[dict[str, Any]] = Field(default_factory=list)


Impl = Annotated[Union[ImplCode, ImplDeclarative], Field(discriminator="kind")]


class IRFunction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    description: str = ""
    params_schema: dict[str, Any] = Field(default_factory=dict)
    return_schema: dict[str, Any] | None = None
    action_type: str | None = None
    effects: list[str] = Field(default_factory=list)
    event: str = ""
    impl: Impl


class IRUi(BaseModel):
    """UI section of an IR app — a list of declared panels."""
    model_config = ConfigDict(extra="forbid")
    panels: list[IRPanel] = Field(default_factory=list)


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
    functions: list[IRFunction] = Field(default_factory=list)
    ui: IRUi | None = None
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
