"""Imperal Cloud SDK — build extensions for the Imperal platform."""
from imperal_sdk.extension import (
    Extension, ToolDef, SignalDef, ScheduleDef,
    LifecycleHook, HealthCheckDef, WebhookDef, EventHandlerDef, ExposedMethod, TrayDef,
)
from imperal_sdk.context import Context
from imperal_sdk.auth import ImperalAuth, AuthError, User
from imperal_sdk.manifest import generate_manifest, save_manifest
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk import ui
from imperal_sdk.runtime.llm_provider import get_llm_provider, LLMProvider, LLMConfig, LLMUsage
from imperal_sdk.runtime.message_adapter import MessageAdapter
from imperal_sdk.extensions.client import ExtensionsClient, CircularCallError

# v1.0.0 types
from imperal_sdk.errors import (
    ImperalError, APIError, NotFoundError, RateLimitError,
    ValidationError, ExtensionError, QuotaExceededError,
    SkeletonAccessForbidden,
)
from imperal_sdk.types import (
    Page, ChatResult, FunctionCall, TaskStatus,
    Document, CompletionResult, LimitsResult, SubscriptionInfo,
    BalanceInfo, FileInfo, HTTPResponse,
    Event, WebhookRequest, WebhookResponse, HealthStatus,
)
from imperal_sdk.protocols import ExtensionProtocol
from imperal_sdk.validator import validate_extension, ValidationReport, ValidationIssue
from imperal_sdk.validator_v1_6_0 import (
    validate_source_tree,
    validate_manifest_v1_6_0,
)

__version__ = "1.6.2"

__all__ = [
    # Core
    "Extension", "ToolDef", "SignalDef", "ScheduleDef",
    "LifecycleHook", "HealthCheckDef", "WebhookDef", "EventHandlerDef", "ExposedMethod", "TrayDef",
    "Context", "ImperalAuth", "AuthError", "User",
    "ActionResult",
    "generate_manifest", "save_manifest",
    # IPC
    "ExtensionsClient", "CircularCallError",
    # LLM
    "get_llm_provider", "LLMProvider", "LLMConfig", "LLMUsage", "MessageAdapter",
    # Errors
    "ImperalError", "APIError", "NotFoundError", "RateLimitError",
    "ValidationError", "ExtensionError", "QuotaExceededError",
    "SkeletonAccessForbidden",
    # Types
    "Page", "ChatResult", "FunctionCall", "TaskStatus",
    "Document", "CompletionResult", "LimitsResult", "SubscriptionInfo",
    "BalanceInfo", "FileInfo", "HTTPResponse",
    "Event", "WebhookRequest", "WebhookResponse", "HealthStatus",
    # Protocol + Validator
    "ExtensionProtocol", "validate_extension", "ValidationReport", "ValidationIssue",
    "validate_source_tree", "validate_manifest_v1_6_0",
    # UI
    "ui",
]
