"""The shell-tool contract: one name, one description and one parameter set per tool, for every shell (ICNLI §3.5).

Until 6.7.0 three hand-written layers described the same tools -- the kernel's LOCAL_TOOL_DEFS (what Webbee's model
sees), webbee's executor, imperal-mcp's server -- and drifted (checkpoint in seven places, `diff` vs
`checkpoint_diff`, `grep` vs `grep_code`, a read_file window honoured in one shell and not the other). The contract is
data (``schemas/tool_contract.json``); the kernel builds LOCAL_TOOL_DEFS from ``as_function_schema``, imperal-mcp its
tool list from ``as_mcp_schema``, webbee's executor answers every tool whose ``shells`` hold "webbee".
"""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class ShellTool:
    name: str
    description: str
    params: dict                    # JSON-schema properties
    required: tuple
    executed_by: str                # "client" (the shell runs it) or "kernel" (the kernel answers it)
    shells: frozenset               # of "webbee", "mcp"
    effect: str = "read"            # read | write | run (a command: judged by what it runs) | snapshot (shadow only)


@functools.lru_cache(maxsize=1)
def _contract() -> dict:
    raw = resources.files("imperal_sdk").joinpath("schemas/tool_contract.json").read_text(encoding="utf-8")
    out = {}
    for name, d in json.loads(raw).items():
        out[name] = ShellTool(name=name, description=d["description"], params=dict(d.get("params") or {}),
                              required=tuple(d.get("required") or ()), executed_by=d.get("executed_by", "client"),
                              shells=frozenset(d.get("shells") or ()), effect=str(d.get("effect") or "read"))
    return out


def shell_tools(shell: str | None = None) -> list:
    """Every tool of the contract, or those of one shell ("webbee" / "mcp"), by name."""
    return [t for _, t in sorted(_contract().items()) if shell is None or shell in t.shells]


def names_by_effect(effect: str, shell: str | None = None, executed_by: str | None = None) -> frozenset:
    """The tools of one effect (read / write / run / snapshot) -- the one list every reader of "which tools read, which
    write" takes, never its own copy (the kernel kept six: working_set, step_frame, tenant_vault_activity, ...).
    ``executed_by``: only those the client ("client") or the kernel ("kernel") answers."""
    return frozenset(t.name for t in shell_tools(shell)
                     if t.effect == effect and (executed_by is None or t.executed_by == executed_by))


def tool(name: str) -> ShellTool:
    return _contract()[name]


def _schema(t: ShellTool) -> dict:
    s = {"type": "object", "properties": dict(t.params)}
    if t.required:
        s["required"] = list(t.required)
    return s


def as_function_schema(t: ShellTool) -> dict:
    """The kernel's tool shape (what LOCAL_TOOL_DEFS holds): ``{name, description, input_schema}``."""
    return {"name": t.name, "description": t.description, "input_schema": _schema(t)}


# said once in imperal-mcp's server instructions, not in every tool's listing (measured 2026-11-13: 2 521 characters of
# every session; 2026-11-15 the contract's own words: 2 237)
EXPLAINED_ONCE = ("root", "target")


def as_mcp_schema(t: ShellTool) -> dict:
    """An MCP tool: ``{name, description, inputSchema}`` -- the parameters the server instructions explain once carry
    their type here, not their description."""
    s = _schema(t)
    s["properties"] = {n: ({k: v for k, v in f.items() if k != "description"} if n in EXPLAINED_ONCE else f)
                       for n, f in s["properties"].items()}
    return {"name": t.name, "description": t.description, "inputSchema": s}
