"""Imperal SDK shared types."""
from imperal_sdk.types.action_result import ActionResult
from imperal_sdk.types.chat_result import ChatResult, FunctionCall
from imperal_sdk.types.models import (
    Document, CompletionResult, LimitsResult, SubscriptionInfo,
    BalanceInfo, FileInfo, HTTPResponse,
)
from imperal_sdk.types.pagination import Page
from imperal_sdk.types.events import Event, WebhookRequest, WebhookResponse
from imperal_sdk.types.health import HealthStatus
from imperal_sdk.types.contributions import Panel, Widget, Command, ContextMenu, Setting, Theme
from imperal_sdk.types.contracts import (
    ActionResultModel, EventModel,
    validate_action_result_dict, validate_event_dict,
    get_action_result_schema, get_event_schema,
    ACTION_RESULT_SCHEMA, EVENT_SCHEMA,
)

__all__ = [
    "ActionResult", "ChatResult", "FunctionCall", "Page",
    "Document", "CompletionResult", "LimitsResult", "SubscriptionInfo",
    "BalanceInfo", "FileInfo", "HTTPResponse",
    "Event", "WebhookRequest", "WebhookResponse", "HealthStatus",
    "Panel", "Widget", "Command", "ContextMenu", "Setting", "Theme",
    # Cross-boundary contracts (v1.5.10+)
    "ActionResultModel", "EventModel",
    "validate_action_result_dict", "validate_event_dict",
    "get_action_result_schema", "get_event_schema",
    "ACTION_RESULT_SCHEMA", "EVENT_SCHEMA",
]
