# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Imperal Cloud SDK — build extensions for the Imperal platform."""
from imperal_sdk.extension import Extension, ToolDef, SignalDef, ScheduleDef
from imperal_sdk.context import Context
from imperal_sdk.auth import ImperalAuth, AuthError, User
from imperal_sdk.manifest import generate_manifest, save_manifest

__version__ = "0.1.0"

__all__ = [
    "Extension", "ToolDef", "SignalDef", "ScheduleDef",
    "Context", "ImperalAuth", "AuthError", "User",
    "generate_manifest", "save_manifest",
]
