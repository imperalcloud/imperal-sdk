# -*- coding: utf-8 -*-
# Copyright (c) 2026 Imperal, Inc.
# Licensed under the Apache-2.0 License.
"""ICNLI Quantum SDK v6.0 — The Universal Zero-Boilerplate Application Engine.

Empowers developers to build next-generation AI Cloud OS applications with:
1. Zero-Manifest: 100% automatic type-to-schema extraction from Python signatures.
2. Auto-IR (UI-as-Data): Automatic projection of returns into reactive Declarative IR.
3. Ambient Context: Automatic runtime injection of Context, Store, Storage, AI.
4. Universal Compatibility: Python 3.6+ through 3.14+ runtime execution.
5. 100% Backwards Compatibility with Extension & ChatExtension v5.x.
"""
import asyncio
import functools
import inspect
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

try:
    from typing import get_type_hints
except ImportError:
    get_type_hints = None

from imperal_sdk.extension import Extension, ToolDef
from imperal_sdk.context import Context
from imperal_sdk.types.identity import UserContext, TenantContext
from imperal_sdk.auto_ui import project_to_declarative_ir

DEFAULT_QUANTUM_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-atom">'
    '<circle cx="12" cy="12" r="1"/>'
    '<path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5Z"/>'
    '<path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5Z"/>'
    '</svg>'
)


def _python_type_to_json_schema(py_type):
    # type: (Any) -> Dict[str, Any]
    """Convert Python typing constructs to standard JSON Schema properties."""
    if py_type in (str, Optional[str]):
        return {"type": "string"}
    elif py_type in (int, Optional[int]):
        return {"type": "integer"}
    elif py_type in (float, Optional[float]):
        return {"type": "number"}
    elif py_type in (bool, Optional[bool]):
        return {"type": "boolean"}
    
    origin = getattr(py_type, "__origin__", None)
    if origin is list or py_type is list or (origin is not None and str(origin).endswith("List")):
        args = getattr(py_type, "__args__", None)
        item_type = _python_type_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_type}
    elif origin is dict or py_type is dict or (origin is not None and str(origin).endswith("Dict")):
        return {"type": "object"}
    return {"type": "string"}


def create_ambient_context(user_id="ambient_user"):
    # type: (str) -> Context
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
    """High-level ICNLI Quantum Application.
    
    Zero-manifest, auto-schema, ambient-context, auto-IR enabled container.
    Inherits from `Extension` for 100% backward compatibility with all
    existing Imperal Cloud kernel, dispatch, and validation pipelines.
    Supports Python 3.6 through Python 3.14+.
    """

    def __init__(
        self,
        app_id,
        name="",
        description="",
        category="general",
        icon="",
        version="1.0.0",
        system=False,
        **kwargs
    ):
        display_name = name or app_id.replace("-", " ").title()
        desc = description or "ICNLI Autonomous Application for {} operations across the cloud.".format(display_name)
        if len(desc) < 40:
            desc = "{} Fully compliant with the ICNLI Agentic OS specification.".format(desc)

        effective_icon = icon or DEFAULT_QUANTUM_ICON

        super(App, self).__init__(
            app_id=app_id,
            version=version,
            display_name=display_name,
            description=desc,
            icon=effective_icon,
            actions_explicit=True,
            system=system,
            **kwargs
        )
        self.category = category
        self._tool_handlers = {}  # type: Dict[str, Callable]
        self._tool_schemas = {}   # type: Dict[str, Dict[str, Any]]

    def tool(
        self,
        name=None,
        description=None,
        pricing=1,
        destructive=False,
        scopes=None,
        chain_callable=True,
    ):
        """Register a Python function as an ICNLI Autonomous Tool.

        Extracts parameters, JSON Schema types, docstring description,
        and scopes automatically from the function signature.
        Supports Python 3.6 through 3.14+.
        """
        def decorator(fn):
            tool_name = name or fn.__name__
            tool_desc = description or (fn.__doc__ or "").strip() or "Execute {}".format(tool_name)

            sig = inspect.signature(fn)
            type_hints = {}
            if get_type_hints is not None:
                try:
                    type_hints = get_type_hints(fn)
                except Exception:
                    type_hints = getattr(fn, "__annotations__", {})
            else:
                type_hints = getattr(fn, "__annotations__", {})

            properties = {}
            required = []
            context_param_name = None

            for param_name, param in sig.parameters.items():
                param_type = type_hints.get(param_name, param.annotation)
                if param_type in (Context, Optional[Context]) or param_name in ("ctx", "context"):
                    context_param_name = param_name
                    continue  # Ambient context is NOT exposed to LLM schema

                schema = _python_type_to_json_schema(param_type)
                schema["description"] = "Argument {}".format(param_name)
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
                "scopes": scopes or ["{}:{}".format(self.app_id, tool_name)],
            }

            is_async = inspect.iscoroutinefunction(fn)

            def _inject_context(args, kwargs):
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

            def _postprocess_res(res):
                if isinstance(res, dict) and "_ui" not in res and "declarative_ui" not in res:
                    ui_proj = project_to_declarative_ir(res, title=tool_name.replace("_", " ").title())
                    if ui_proj:
                        res["_ui"] = ui_proj
                return res

            if is_async:
                @functools.wraps(fn)
                async def wrapper(*args, **kwargs):
                    _inject_context(args, kwargs)
                    res = await fn(*args, **kwargs)
                    return _postprocess_res(res)
            else:
                @functools.wraps(fn)
                def wrapper(*args, **kwargs):
                    _inject_context(args, kwargs)
                    res = fn(*args, **kwargs)
                    return _postprocess_res(res)

            self._tool_handlers[tool_name] = wrapper

            default_scopes = scopes or ["{}:{}".format(self.app_id, tool_name)]
            self.tools[tool_name] = ToolDef(
                name=tool_name,
                func=wrapper,
                scopes=default_scopes,
                description=tool_desc,
            )
            return wrapper

        return decorator

    def to_manifest(self):
        # type: () -> Dict[str, Any]
        """Synthesize full ICNLI Compliant Manifest dictionary dynamically."""
        return {
            "manifest_version": "1.0.0",
            "app_id": self.app_id,
            "name": self.display_name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "entrypoint": "app:app",
            "tools": list(self._tool_schemas.values()),
            "permissions": {"scopes": list(set([s for t in self._tool_schemas.values() for s in t.get("scopes", [])]))},
            "system": self.system,
        }
