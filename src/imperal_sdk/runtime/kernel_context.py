"""KernelContext — resolved ONCE per message, passed through entire pipeline.

Replaces 3-5x duplicate resolution of identity/config/settings per message.
Created by resolve_kernel_context Temporal activity.
Consumed by execute_sdk_tool, Hub, _execute_extension, ContextFactory.
"""
import dataclasses
from dataclasses import dataclass, field, asdict


_LANG_NAMES = {
    "ru": "Russian", "en": "English", "es": "Spanish", "fr": "French",
    "de": "German", "ar": "Arabic", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "pt": "Portuguese", "it": "Italian", "tr": "Turkish",
}


@dataclass(slots=True)
class KernelContext:
    """Resolved ONCE per message. Passed through entire pipeline."""

    # ── Identity (Auth Gateway /v1/users/{id}, Redis cached 5min) ──
    user_id: str
    email: str
    role: str
    scopes: list[str]
    attributes: dict
    tenant_id: str
    is_active: bool = True

    # ── Config (Auth Gateway /v1/internal/config/resolve, Redis cached 5min) ──
    resolved_config: dict = field(default_factory=dict)

    # ── Confirmation & KAV (Auth Gateway /v1/internal/users/{id}/settings) ──
    confirmation_enabled: bool = False
    confirmation_actions: dict = field(default_factory=dict)
    confirmation_ttl: int = 300
    kav_max_retries: int = 2

    # ── Time (computed from attributes.timezone) ──
    timezone: str = "UTC"
    now_utc: str = ""
    now_local: str = ""
    hour_local: int = 0
    is_business_hours: bool = False

    # ── Language (Redis imperal:user_lang:{user_id}, updated by Hub LLM) ──
    language: str = ""
    language_name: str = ""

    # ── Access (derived from load_all_user_extensions result) ──
    allowed_apps: set[str] = field(default_factory=set)

    # ── Routing (set once by Hub after LLM classification) ──
    intent_type: str = "read"
    is_automation: bool = False

    def to_dict(self) -> dict:
        """Serialize for Temporal activity return (JSON-compatible)."""
        d = asdict(self)
        d["allowed_apps"] = list(d["allowed_apps"])
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "KernelContext":
        """Deserialize from Temporal activity result."""
        data = dict(data)  # don't mutate original
        data["allowed_apps"] = set(data.get("allowed_apps", []))
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def lang_name(self) -> str:
        """Language display name from code. Fallback to uppercase code."""
        if self.language_name:
            return self.language_name
        return _LANG_NAMES.get(self.language, self.language.upper()) if self.language else ""
