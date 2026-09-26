# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""ICNLI Quantum SDK v6.0 — The Universal Zero-Boilerplate Application Engine.

Empowers developers to build next-generation AI Cloud OS applications with:
1. Zero-Manifest: 100% automatic type-to-schema extraction from Python signatures.
2. Auto-IR (UI-as-Data): Automatic projection of returns into reactive Declarative UI.
3. Ambient Context: Automatic runtime injection of Context, Store, Storage, AI.
4. 100% Backwards Compatibility with Extension & ChatExtension v5.16+.
"""
from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union, get_type_hints

from imperal_sdk.extension import Extension, ToolDef
from imperal_sdk.context import Context
from imperal_sdk.types.identity import UserContext, TenantContext
from imperal_sdk.auto_ui import project_to_declarative_ir


DEFAULT_QUANTUM_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>'
    '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>'
    '<line x1="12" y1="22.08" x2="12" y2="12"/>'
    '</svg>'
)


def _python_type_to_json_schema(py_type: Any) -> Dict[str, Any]:
    """Convert Python typing constructs to standard JSON Schema properties."""
    if py_type in (str, Optional[str]):
        return {"type": "string"}
    elif py_type in (int, Optional[int]):
        return {"type": "integer"}
    elif py_type in (float, Optional[float]):
        return {"type": "number"}
    elif py_type in (bool, Optional[bool]):
        return {"type": "boolean"}
    elif getattr(py_type, "__origin__", None) is list or py_type is list:
        args = getattr(py_type, "__args__", None)
        item_type = _python_type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_type}
    elif getattr(py_type, "__origin__", None) is dict or py_type is dict:
        return {"type": "object"}
    return {"type": "string"}


def create_ambient_context(user_id: str = "ambient_user") -> Context:
    """Create a default Context for local invocation or testing."""
    return Context(
        user=UserContext(
            imperal_id=user_id,
            tenant_id="ambient_tenant",
            email="ambient@imperal.io",
            role="admin",
        ),
        tenant=TenantContext(
            tenant_id="ambient_tenant",
            name="Ambient Tenant",
        ),
    )


class App(Extension):
    """Next-Generation Zero-Boilerplate Application Engine (ICNLI Quantum SDK v6.0)."""

    def __init__(
        self,
        app_id: str,
        name: str = "",
        description: str = "",
        category: str = "general",
        icon: str = "",
        version: str = "1.0.0",
        *,
        system: bool = False,
        **kwargs: Any,
    ) -> None:
        display_name = name or app_id.replace("-", " ").title()
        desc = description or f"ICNLI Autonomous Application for {display_name} operations across the cloud."
        if len(desc) < 40:
            desc = f"{desc} Fully compliant with the ICNLI Agentic OS specification."

        effective_icon = icon or DEFAULT_QUANTUM_ICON

        super().__init__(
            app_id=app_id,
            version=version,
            display_name=display_name,
            description=desc,
            icon=effective_icon,
            actions_explicit=True,
            system=system,
            **kwargs,
        )
        self.category = category
        self._tool_handlers: Dict[str, Callable] = {}
        self._tool_schemas: Dict[str, Dict[str, Any]] = {}

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        pricing: int = 1,
        destructive: bool = False,
        scopes: Optional[List[str]] = None,
        chain_callable: bool = True,
    ) -> Callable:
        """Register a Python function as an ICNLI Autonomous Tool.

        Extracts parameters, JSON Schema types, docstring description,
        and scopes automatically from the function signature.
        """
        def decorator(fn: Callable) -> Callable:
            tool_name = name or fn.__name__
            tool_desc = description or (fn.__doc__ or "").strip() or f"Execute {tool_name}"

            sig = inspect.signature(fn)
            try:
                type_hints = get_type_hints(fn)
            except Exception:
                type_hints = {}

            properties: Dict[str, Any] = {}
            required: List[str] = []
            context_param_name: Optional[str] = None

            for param_name, param in sig.parameters.items():
                param_type = type_hints.get(param_name, param.annotation)
                if param_type in (Context, Optional[Context]) or param_name in ("ctx", "context"):
                    context_param_name = param_name
                    continue  # Ambient context is NOT exposed to LLM schema

                schema = _python_type_to_json_schema(param_type)
                schema["description"] = f"Argument {param_name}"
                if param.default is not inspect.Parameter.empty:
                    schema["default"] = param.default
                else:
                    required.append(param_name)
                properties[param_name] = schema

            parameters_schema = {
                "type": "object",
                "properties": properties,
            }
            if required:
                parameters_schema["required"] = required

            action_type = "destructive" if destructive else "write"

            self._tool_schemas[tool_name] = {
                "name": tool_name,
                "description": tool_desc,
                "parameters": parameters_schema,
                "pricing": pricing,
                "action_type": action_type,
                "destructive": destructive,
                "chain_callable": chain_callable,
                "scopes": scopes or [f"{self.app_id}:{tool_name}"],
            }

            is_async = inspect.iscoroutinefunction(fn)

            def _inject_context(args: tuple, kwargs: dict):
                if context_param_name and context_param_name not in kwargs:
                    found = False
                    for a in args:
                        if isinstance(a, Context):
                            kwargs[context_param_name] = a
                            found = True
                            break
                    if not found:
                        try:
                            kwargs[context_param_name] = create_ambient_context()
                        except Exception:
                            kwargs[context_param_name] = None

            def _postprocess_res(res: Any):
                if isinstance(res, dict) and "_ui" not in res and "declarative_ui" not in res:
                    ui_proj = project_to_declarative_ir(res, title=tool_name.replace("_", " ").title())
                    if ui_proj:
                        res["_ui"] = ui_proj
                return res

            if is_async:
                @functools.wraps(fn)
                async def wrapper(*args: Any, **kwargs: Any) -> Any:
                    _inject_context(args, kwargs)
                    res = await fn(*args, **kwargs)
                    return _postprocess_res(res)
            else:
                @functools.wraps(fn)
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    _inject_context(args, kwargs)
                    res = fn(*args, **kwargs)
                    return _postprocess_res(res)

            self._tool_handlers[tool_name] = wrapper

            default_scopes = scopes or [f"{self.app_id}:{tool_name}"]
            self.tools[tool_name] = ToolDef(
                name=tool_name,
                func=wrapper,
                scopes=default_scopes,
                description=tool_desc,
            )
            return wrapper

        return decorator

    def to_manifest(self) -> Dict[str, Any]:
        """Synthesize full ICNLI Compliant Manifest dictionary dynamically."""
        return {
            "manifest_version": "1.0.0",
            "app_id": self.app_id,
            "name": self.display_name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "actions_explicit": True,
            "system": self.system,
            "tools": list(self._tool_schemas.values()),
        }
