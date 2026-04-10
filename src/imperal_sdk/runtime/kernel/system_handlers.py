# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Kernel system tool handlers — discover_tools, system_chat, hub_chat proxy,
capability injection, skeleton pruning.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from imperal_sdk.runtime.kernel_context import KernelContext as _KernelContext

log = logging.getLogger(__name__)


# ── Skeleton Pruning ──────────────────────────────────────────────


def _prune_skeleton(skeleton_data: dict, target_app_id: str) -> dict:
    """Guard 4: Keep only relevant skeleton sections for target extension.

    Hub/system tools see everything. Individual extensions see only their own
    skeleton sections + kernel context (_context) + shared data (email_accounts).
    """
    if not skeleton_data or not isinstance(skeleton_data, dict):
        return skeleton_data or {}
    if target_app_id in ("__system__", "imperal-hub"):
        return skeleton_data

    pruned = {}
    for key, value in skeleton_data.items():
        if key == "_context":
            pruned[key] = value
        elif key == "email_accounts":
            pruned[key] = value
        elif isinstance(value, dict) and value.get("app_id"):
            if value["app_id"] == target_app_id:
                pruned[key] = value
        else:
            pruned[key] = value

    if len(pruned) != len(skeleton_data):
        log.debug(f"Skeleton pruned: {len(skeleton_data)} -> {len(pruned)} keys for {target_app_id}")

    return pruned


# ── Capability Boundary Injection ─────────────────────────────────


def _inject_capability_boundary(ctx, app_id: str, ext, catalog: Any = None):
    """Kernel injects ICNLI integrity protocol into every extension context.

    Two parts:
    1. Capability boundary — what this extension CAN and CANNOT do
    2. ICNLI integrity rules — zero hallucination, verified actions only

    Injected into skeleton._context so extension's LLM sees it in system prompt."""
    skeleton = ctx.skeleton_data if ctx.skeleton_data else {}
    _context = skeleton.get("_context", {})

    my_tools = list(ext.tools.keys())

    other_capabilities = []
    if catalog and catalog.loaded:
        for t in catalog.tools:
            if t["app_id"] != app_id:
                other_capabilities.append({
                    "app_id": t["app_id"],
                    "name": t["name"],
                    "description": t.get("description", "")[:100],
                })

    _context["_capability_boundary"] = {
        "you_are": app_id,
        "your_tools": my_tools,
        "your_tool_count": len(my_tools),
        "other_extensions": other_capabilities,
        "rule": (
            f"You are extension '{app_id}' inside Imperal Cloud AI OS. Your tools: {my_tools}. "
            f"Use your tools to fulfill user requests. If a request is outside your tools, "
            f"respond honestly about what you can and cannot do — the system will route elsewhere. "
            f"NEVER pretend you performed an action you don't have a tool for. "
            f"The OS supports chaining multiple extensions and AI Cloud Agents (automated rules with cron/event triggers)."
        ),
    }

    # ICNLI Integrity Protocol — injected into EVERY extension by kernel
    _context["_icnli_integrity"] = {
        "protocol": "ICNLI",
        "version": "1.0",
        "rules": [
            "ONLY report what functions actually returned. If a function returned an error, report the error.",
            "NEVER fabricate data, URLs, links, tokens, IDs, or any information not returned by a function.",
            "NEVER claim an action succeeded unless the function result explicitly confirms success.",
            "NEVER generate OAuth URLs, authorization links, or credentials — you do not have this capability.",
            "If unsure whether an action succeeded, call a read/list function to verify before reporting.",
            "If you cannot perform what the user asked, say what you cannot do and which extension handles it.",
            "NEVER apologize repeatedly or contradict yourself. State facts once.",
            "NEVER answer questions from cached context or conversation history — always call a function for fresh data.",
            "Before claiming a resource is 'not connected' or 'not available', ALWAYS check via status/list function first. The skeleton contains connected accounts — read it before making claims.",
            "CRITICAL: ALWAYS respond in the SAME language as the user's last message. Russian → Russian. English → English. NEVER mix languages in one response. This is a KERNEL-ENFORCED rule.",
        ],
        "enforcement": "KERNEL — these rules are enforced by the ICNLI OS. Violation = system integrity failure.",
    }

    # ── Skeleton Freshness Validation (ICNLI L6 compliance) ──────
    # Scan skeleton sections for stale data and inject warnings.
    # Extensions and LLM see _stale_sections so they know to be cautious.
    import time as _fresh_time
    _stale_sections = []
    for _sec_name, _sec_data in skeleton.items():
        if _sec_name.startswith("_"):
            continue
        if isinstance(_sec_data, dict) and "_freshness" in _sec_data:
            _fr = _sec_data["_freshness"]
            _ttl_rem = _fr.get("ttl_remaining", -1)
            _refreshed_at = _fr.get("refreshed_at")
            _ttl_orig = _sec_data.get("_ttl_seconds", 0)
            # Mark stale if: TTL remaining < 10% of original OR refreshed_at > 2x TTL ago
            if _ttl_orig and _ttl_rem >= 0 and _ttl_rem < _ttl_orig * 0.1:
                _stale_sections.append({"section": _sec_name, "ttl_remaining": _ttl_rem, "reason": "ttl_expiring"})
            elif _refreshed_at and _ttl_orig and (_fresh_time.time() - _refreshed_at) > _ttl_orig * 2:
                _stale_sections.append({"section": _sec_name, "age_seconds": int(_fresh_time.time() - _refreshed_at), "reason": "overdue_refresh"})
    if _stale_sections:
        _context["_stale_sections"] = _stale_sections
        _context["_freshness_warning"] = (
            "Some skeleton data may be outdated. If the user asks about real-time state, "
            "call a function to get fresh data instead of relying on skeleton cache."
        )

    skeleton["_context"] = _context
    ctx.skeleton_data = skeleton


# ── System Tools ──────────────────────────────────────────────────


async def _handle_discover_tools(tool_input: dict, catalog: Any = None) -> dict:
    """Handle discover_tools system call — semantic search over tool catalog."""
    if catalog is None or not catalog.loaded:
        log.warning("discover_tools called but catalog not loaded")
        return {"response": {"tools_found": 0, "tools": [], "error": "Catalog not available"}}

    message = tool_input.get("message", "")
    context = tool_input.get("context", {})
    top_k = context.get("top_k", 5)
    session_tools = context.get("session_tools", [])

    user_info = tool_input.get("user", {})
    user_scopes = user_info.get("scopes", ["*"])
    results = await catalog.search(
        query=message,
        top_k=min(top_k, 10),
        session_tools=session_tools,
        user_scopes=user_scopes,
    )

    log.info(f"discover_tools: query='{message[:60]}', found={len(results)}")

    return {
        "response": {
            "tools_found": len(results),
            "tools": results,
        }
    }


# ── Hub/System Chat Handlers ─────────────────────────────────────


async def _handle_hub_chat(tool_input: dict, kctx: _KernelContext, catalog: Any = None) -> dict:
    """Handle hub_chat — ICNLI OS kernel orchestrator."""
    from imperal_sdk.runtime.hub import handle_hub_chat
    from imperal_sdk.runtime.relations import load_app_relations

    relations = await load_app_relations(kctx.tenant_id)

    return await handle_hub_chat(
        tool_input=tool_input,
        kctx=kctx,
        catalog=catalog,
        relations=relations,
    )


async def _handle_system_chat(tool_input: dict, catalog: Any = None) -> dict:
    """Handle system_chat — OS-level conversation with full capability awareness.

    The system knows ALL its capabilities from the ToolCatalog.
    Used for greetings, "what can you do?", and any message that
    doesn't match a specific extension tool.

    CRITICAL: system_chat is READ-ONLY. It cannot execute any actions.
    It can only navigate users to the right extension.
    """
    message = tool_input.get("message", "")
    history = tool_input.get("history", [])
    skeleton = tool_input.get("skeleton", {})
    user_info = tool_input.get("user", {})

    # Build capabilities list from live catalog
    capabilities = []
    if catalog and catalog.loaded:
        # Group tools by extension
        ext_tools: dict[str, list[str]] = {}
        for t in catalog.tools:
            app = t.get("app_display_name", t.get("app_id", "unknown"))
            desc = t.get("description", t.get("name", ""))
            ext_tools.setdefault(app, []).append(desc)

        for app_name, tools in ext_tools.items():
            tool_list = "; ".join(t for t in tools if t)
            if tool_list:
                capabilities.append(f"- **{app_name}**: {tool_list}")
            else:
                capabilities.append(f"- **{app_name}**")

    capabilities_text = "\n".join(capabilities) if capabilities else "No extensions installed."

    # Build skeleton context (known issues, alerts)
    skeleton_context = ""
    ctx_data = skeleton.get("_context", {})
    for key, val in skeleton.items():
        if key.startswith("_") or val is None:
            continue
        if isinstance(val, str) and val.strip():
            skeleton_context += f"- {key}: {val[:200]}\n"
        elif isinstance(val, dict):
            summary = str(val)[:200]
            skeleton_context += f"- {key}: {summary}\n"

    # User identity (resolved by kernel)
    user_email = user_info.get("email", "unknown")
    user_role = user_info.get("role", "user")
    user_id_display = user_info.get("id", "")
    user_identity = f"CURRENT USER: {user_email} (role: {user_role}, id: {user_id_display})"

    system_prompt = f"""You are the Imperal Cloud ICNLI OS — an intelligent cloud operating system.
You are the system shell, not an extension or app. You help users navigate to the right extension.

{user_identity}

AVAILABLE EXTENSIONS (live from catalog — these are the ONLY things that exist):
{capabilities_text}

{f"SYSTEM CONTEXT:{chr(10)}{skeleton_context}" if skeleton_context else ""}

ABSOLUTE RULES — VIOLATION IS SYSTEM FAILURE:
1. You are READ-ONLY. You CANNOT execute any actions, commands, or operations.
2. You CANNOT suspend, activate, delete, create, update, or modify ANYTHING.
3. You CANNOT generate URLs, OAuth links, tokens, credentials, or authorization links.
4. You CANNOT connect accounts, send emails, manage users, or perform any operation.
5. If the user asks you to DO something (suspend, activate, connect, show data, etc.) — tell them WHICH EXTENSION handles it. Example: "This is handled by System Admin. Please ask it directly — just say 'suspend gmail extension'."
6. You can ONLY: greet users, explain what extensions are available, and direct users to the right extension.
7. NEVER say "I did it", "Done", "Suspended", "Activated", or any confirmation of an action. You cannot do actions.
8. NEVER fabricate or invent any data, links, or results.
9. When asked "what can you do?" — list ONLY the extensions from the catalog above. Nothing else.
10. Respond in the user's language. No emojis. "Imperal" not "Imperial".
11. Be concise. One or two sentences max. Direct the user, don't explain at length."""

    # Build messages for Haiku
    messages = []
    for h in history[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        from imperal_sdk.runtime.llm_provider import get_llm_provider
        provider = get_llm_provider()
        resp = await provider.create_message(
            max_tokens=1024,
            purpose="navigation",
            user_id=user_info.get("id", ""),
            system=system_prompt,
            messages=messages,
        )
        response_text = resp.content[0].text if resp.content else "Hello! How can I help you?"
        log.info(f"system_chat: user='{message[:60]}', response_len={len(response_text)}")
        return {"response": response_text}

    except Exception as e:
        log.error(f"system_chat error: {e}")
        return {"response": "Hello! I'm the Imperal Cloud OS. How can I help you today?"}
