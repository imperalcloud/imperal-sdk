"""Imperal Cloud SDK — build extensions for the Imperal platform."""
from imperal_sdk.extension import Extension, ToolDef, SignalDef, ScheduleDef
from imperal_sdk.context import Context
from imperal_sdk.auth import ImperalAuth, AuthError, User
from imperal_sdk.manifest import generate_manifest, save_manifest
from imperal_sdk.runtime import ExtensionLoader, ContextFactory, execute_sdk_tool, init_runtime
from imperal_sdk.chat import ChatExtension
from imperal_sdk.chat.action_result import ActionResult

__version__ = "0.2.0"

__all__ = [
    "Extension", "ToolDef", "SignalDef", "ScheduleDef",
    "Context", "ImperalAuth", "AuthError", "User",
    "ChatExtension", "ActionResult",
    "generate_manifest", "save_manifest",
    "ExtensionLoader", "ContextFactory", "execute_sdk_tool", "init_runtime",
]
