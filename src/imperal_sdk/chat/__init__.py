"""imperal_sdk.chat — shared narration, action results, error codes, guards.

v2.0.0: ChatExtension class + per-ext LLM loop removed. Extensions are
pure tool providers; kernel Narrator composes all user-facing prose.
Remaining surface: types, contracts, narration emission schema, identity
guard helpers, error codes, federal invariant primitives.
"""
from imperal_sdk.chat.action_result import ActionResult
from imperal_sdk.chat.error_codes import (
    ERROR_TAXONOMY,
    VALIDATION_MISSING_FIELD,
    VALIDATION_TYPE_ERROR,
    UNKNOWN_TOOL,
    UNKNOWN_SUB_FUNCTION,
    PERMISSION_DENIED,
    BACKEND_TIMEOUT,
    BACKEND_5XX,
    RATE_LIMITED,
    INTERNAL,
)
from imperal_sdk.chat.kernel_primitives import (
    HUB_DISPATCH_TOOL,
    is_hub_dispatch_tool_use,
)
from imperal_sdk.chat.narration import (
    EMIT_NARRATION_TOOL,
    PerCallVerdict,
    TaskTargets,
    NarrationEmission,
    parse_narration_emission,
)
from imperal_sdk.chat.narration_guard import (
    STRICT_NARRATION_POSTAMBLE,
    format_functions_called_summary,
    augment_system_with_narration_rule,
)

__all__ = [
    # Types / contracts
    "ActionResult",
    # Error taxonomy
    "ERROR_TAXONOMY",
    "VALIDATION_MISSING_FIELD",
    "VALIDATION_TYPE_ERROR",
    "UNKNOWN_TOOL",
    "UNKNOWN_SUB_FUNCTION",
    "PERMISSION_DENIED",
    "BACKEND_TIMEOUT",
    "BACKEND_5XX",
    "RATE_LIMITED",
    "INTERNAL",
    # Federal kernel primitives
    "HUB_DISPATCH_TOOL",
    "is_hub_dispatch_tool_use",
    # Narration emission schema
    "EMIT_NARRATION_TOOL",
    "PerCallVerdict",
    "TaskTargets",
    "NarrationEmission",
    "parse_narration_emission",
    # Narration identity guards
    "STRICT_NARRATION_POSTAMBLE",
    "format_functions_called_summary",
    "augment_system_with_narration_rule",
]
