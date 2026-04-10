"""Context Factory — builds Context objects for extension execution.

Creates the process environment (Context) for each extension tool call,
wiring up all SDK clients (store, ai, skeleton, billing, notify, storage, http, config).
"""
import logging
import os

from imperal_sdk.context import Context, TimeContext
from imperal_sdk.auth.user import User
from imperal_sdk.store.client import StoreClient
from imperal_sdk.ai.client import AIClient
from imperal_sdk.billing.client import BillingClient
from imperal_sdk.skeleton.client import SkeletonClient
from imperal_sdk.notify.client import NotifyClient
from imperal_sdk.storage.client import StorageClient
from imperal_sdk.http.client import HTTPClient
from imperal_sdk.config.client import ConfigClient

log = logging.getLogger(__name__)

_service_token = ""
_gateway_url = ""


class ContextFactory:
    """Creates Context objects for extension tool execution."""

    def __init__(self, gateway_url: str, service_token: str):
        global _service_token, _gateway_url
        _service_token = service_token
        _gateway_url = gateway_url
        self._gateway_url = gateway_url
        self._service_token = service_token

    def _build_context(
        self,
        user: User,
        extension_id: str,
        tenant_id: str,
        resolved_config: dict,
        time_ctx: TimeContext,
        history: list,
        skeleton_data: dict,
    ) -> Context:
        """Shared builder — wires up all SDK clients and returns Context."""
        store = StoreClient(
            gateway_url=self._gateway_url,
            service_token=self._service_token,
            extension_id=extension_id,
            user_id=user.id,
            tenant_id=tenant_id,
        )
        ai = AIClient(
            gateway_url=self._gateway_url,
            service_token=self._service_token,
            extension_id=extension_id,
        )
        billing = BillingClient(
            gateway_url=self._gateway_url,
            service_token=self._service_token,
        )
        skeleton = SkeletonClient(
            gateway_url=self._gateway_url,
            service_token=self._service_token,
            extension_id=extension_id,
            user_id=user.id,
        )
        notify = NotifyClient(
            gateway_url=self._gateway_url,
            service_token=self._service_token,
            user_id=user.id,
        )
        storage = StorageClient(
            gateway_url=self._gateway_url,
            service_token=self._service_token,
            extension_id=extension_id,
            tenant_id=tenant_id,
        )
        http = HTTPClient()
        config = ConfigClient(resolved=resolved_config)

        ctx = Context(
            user=user,
            tenant=tenant_id,
            store=store,
            ai=ai,
            skeleton=skeleton,
            billing=billing,
            notify=notify,
            storage=storage,
            http=http,
            config=config,
            time=time_ctx,
            _extension_id=extension_id,
            _metadata={
                "history": history,
                "skeleton_data": skeleton_data,
            },
        )
        ctx.skeleton_data = skeleton_data
        ctx.history = history
        return ctx

    async def create(
        self,
        user_info: dict,
        extension_id: str,
        history: list = None,
        skeleton_data: dict = None,
        resolved_config: dict = None,
        time_context: dict = None,
    ) -> Context:
        """Build a Context for an extension tool call."""
        user_id = str(user_info.get("id", ""))
        tenant_id = str(user_info.get("tenant_id", "default"))
        scopes = user_info.get("scopes", ["*"])
        attributes = user_info.get("attributes", {})

        user = User(
            id=user_id,
            email=user_info.get("email", ""),
            tenant_id=tenant_id,
            role=user_info.get("role", "user"),
            scopes=scopes if isinstance(scopes, list) else list(scopes),
            attributes=attributes if isinstance(attributes, dict) else {},
            is_active=user_info.get("is_active", True),
        )

        tc = TimeContext()
        if time_context and isinstance(time_context, dict):
            tc = TimeContext(
                timezone=time_context.get("timezone", "UTC"),
                utc_offset=time_context.get("utc_offset", "+00:00"),
                now_utc=time_context.get("now_utc", ""),
                now_local=time_context.get("now_local", ""),
                hour_local=time_context.get("hour_local", 0),
                is_business_hours=time_context.get("is_business_hours", False),
            )

        return self._build_context(
            user=user,
            extension_id=extension_id,
            tenant_id=tenant_id,
            resolved_config=resolved_config or {},
            time_ctx=tc,
            history=history or [],
            skeleton_data=skeleton_data or {},
        )

    async def create_from_kctx(
        self,
        kctx,
        extension_id: str,
        history: list = None,
        skeleton_data: dict = None,
    ) -> Context:
        """Build Context from pre-resolved KernelContext. No HTTP calls.

        Args:
            kctx: KernelContext dataclass (from resolve_kernel_context activity)
            extension_id: app_id of the extension being executed
            history: pre-loaded conversation history
            skeleton_data: pre-loaded skeleton data (already pruned)
        """
        user = User(
            id=kctx.user_id,
            email=kctx.email,
            tenant_id=kctx.tenant_id,
            role=kctx.role,
            scopes=kctx.scopes if isinstance(kctx.scopes, list) else list(kctx.scopes),
            attributes=kctx.attributes if isinstance(kctx.attributes, dict) else {},
            is_active=kctx.is_active,
        )

        tc = TimeContext(
            timezone=kctx.timezone,
            utc_offset="",
            now_utc=kctx.now_utc,
            now_local=kctx.now_local,
            hour_local=kctx.hour_local,
            is_business_hours=kctx.is_business_hours,
        )

        return self._build_context(
            user=user,
            extension_id=extension_id,
            tenant_id=kctx.tenant_id,
            resolved_config=kctx.resolved_config or {},
            time_ctx=tc,
            history=history or [],
            skeleton_data=skeleton_data or {},
        )

    async def destroy(self, ctx) -> None:
        """Cleanup context resources. Called by executor after tool execution."""
        # Close httpx clients if any were opened
        try:
            if hasattr(ctx, 'http') and ctx.http and hasattr(ctx.http, '_client'):
                client = getattr(ctx.http, '_client', None)
                if client and hasattr(client, 'aclose'):
                    await client.aclose()
        except Exception:
            pass
