from __future__ import annotations
"""ICNLI OS Hub — kernel-level cross-app orchestrator.

The Hub is the OS shell. It discovers, dispatches, and combines results
from multiple extensions in a single user request.

Algorithm: DISCOVER (embeddings) → ROUTE (LLM) → DISPATCH → COMBINE
"""
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from imperal_sdk.runtime.kernel_context import KernelContext as _KernelContext

from imperal_sdk.runtime.kernel_context import _LANG_NAMES
from imperal_sdk.runtime.hub.session import (
    _get_hub_redis, _load_session_state, _save_session_state,
    _enrich_if_followup, _update_chain_status, _strip_kernel_context,
)
from imperal_sdk.runtime.hub.chain import (
    _build_chain_step_context, _plan_chain_steps, _is_passthrough,
)
from imperal_sdk.runtime.hub.router import (
    _is_extension_error, _is_capabilities_query, _is_short_ack,
    _route_with_llm, _detect_automation_target, _select_dispatch_targets,
)
from imperal_sdk.runtime.hub.dispatcher import _dispatch_one
from imperal_sdk.runtime.hub.navigator import _hub_navigate, _hub_combine

log = logging.getLogger(__name__)


async def handle_hub_chat(tool_input: dict, kctx: _KernelContext, catalog: Any, relations: dict = None) -> dict:
    """Main Hub entry point. Called by executor when hub_chat dispatched."""
    message = tool_input.get("message", "")
    user_info = tool_input.get("user", {})
    history = tool_input.get("history", [])
    skeleton = tool_input.get("skeleton", {})
    context = tool_input.get("context", {})

    pre_discovered = tool_input.get("_discovered", [])

    # Read user settings from resolved config (Settings AI Behavior sliders)
    _user_settings = kctx.resolved_config.get("user_settings") or {}
    _routing_context = int(_user_settings.get("routing_context", 12) or 12)

    # Language from KernelContext (pre-resolved)
    if kctx.language:
        context["_user_language"] = kctx.language
        context["_user_language_name"] = kctx.language_name

    # Extract allowed extensions for this user (pre-filtered by session_workflow access_policy)
    # Allowed apps from KernelContext (pre-resolved by resolve_kernel_context)
    _user_allowed_apps = kctx.allowed_apps

    # Set automation flag on kctx
    kctx.is_automation = bool(context.get("automation_rule_id"))

    # ── Capabilities query → always navigate (show ALL extensions) ──
    if _is_capabilities_query(message):
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton, routing_context=_routing_context)

    # ── Pending question confirmation → re-dispatch to last extension ──
    # MUST be checked BEFORE short_ack — "да"/"yes" overlap both sets
    # "да", "давай", "покажи", "go ahead" after Webbee asked a question → execute the suggestion
    _confirmation_words = {"да", "давай", "покажи", "конечно", "ага", "yes", "sure", "go ahead", "do it", "show", "please"}
    _msg_lower = message.strip().lower().rstrip("!.")
    if _msg_lower in _confirmation_words:
        _ss = await _load_session_state(user_info.get("id", ""))
        if _ss.get("pending_question") and _ss.get("last_app"):
            _pending = _ss["pending_question"]
            _last = _ss["last_app"]
            log.info(f"Hub: confirmation '{message}' → re-dispatch to {_last} (pending: {_pending[:50]})")
            # Re-dispatch: use the pending question as context for the extension
            message = f"{_pending} — user confirmed: {message}"
            # Don't fall through to LLM routing — we know the target
            if _user_allowed_apps is None or _last in _user_allowed_apps:
                for t in catalog.tools:
                    if t.get("app_id") == _last:
                        context["_suppress_promotion"] = True
                        result = await _dispatch_one(kctx, _last, t["activity_name"],
                                                     message, history, skeleton, context,
                                                     suppress_promotion=True,
                                                     confirmation_bypassed=context.get("_confirmation_bypassed", False))
                        if isinstance(result, dict) and result.get("_handled", True):
                            await _save_session_state(user_info.get("id", ""), _last, result)
                            _out = {"response": result.get("response", ""), **{k: v for k, v in result.items() if k.startswith("_")}}
                            if result.get("_had_function_calls"):
                                _out["_message_type"] = "function_call"
                            return _out
                        break
            # Fallback: treat as normal message
            log.info(f"Hub: confirmation fallback — last_app {_last} not available")

    # ── KERNEL GUARD: Short ack/dismissal → ALWAYS navigate, NEVER dispatch ──
    # Checked AFTER pending question — "да"/"yes" should re-dispatch if pending, navigate if not.
    if _is_short_ack(message):
        log.info(f"Hub: short ack detected ('{message[:30]}') → navigate (no dispatch)")
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton, routing_context=_routing_context)

    # ── Step 1: DISCOVER (embeddings) ─────────────────────────────
    if pre_discovered:
        found_tools = pre_discovered
    elif catalog and catalog.loaded:
        user_scopes = user_info.get("scopes", ["*"])
        found_tools = await catalog.search(
            query=message,
            top_k=5,
            user_scopes=user_scopes,
        )
    else:
        found_tools = []

    # Group by unique app_id — keep best candidate per extension
    all_extensions = {}
    for t in found_tools:
        app_id = t.get("app_id", "")
        score = t.get("relevance", 0)
        if score >= 0.15 and (app_id not in all_extensions or score > all_extensions[app_id].get("relevance", 0)):
            all_extensions[app_id] = t

    # ── Embeddings as OPTIMIZATION, not GATE ─────────────────────
    # High score → FAST PATH (skip LLM, save ~200ms).
    # Low score → LLM routing decides (Haiku handles ANY language).
    # LLM returns "none" → navigate. Embeddings never block LLM.
    is_automation = bool(context.get("automation_rule_id"))
    _max_score = max((t.get("relevance", 0) for t in found_tools), default=0)

    intent_type = "read"  # default intent

    # ── Automation intent detection (keyword-based, no LLM needed) ──
    if is_automation:
        _msg_lower = message.lower()
        _write_kw = ("send", "reply", "create", "forward", "compose", "save", "update",
                     "replace", "modify", "edit", "change", "move", "switch", "set", "put",
                     "отправь", "создай", "ответь", "перешли", "сохрани", "обнови",
                     "замени", "измени", "редактируй", "перемести", "установи")
        _destructive_kw = ("delete", "remove", "archive", "trash", "suspend",
                           "удали", "убери", "заархивируй")
        if any(w in _msg_lower for w in _destructive_kw):
            intent_type = "destructive"
        elif any(w in _msg_lower for w in _write_kw):
            intent_type = "write"
        log.info(f"Hub automation intent: {intent_type} for '{message[:60]}'")

    if not is_automation and catalog and catalog.loaded:
        # Build session hint from state already loaded (avoid duplicate Redis call in _route_with_llm)
        _session_state = await _load_session_state(user_info.get("id", ""))
        _session_hint_str = f"\nLAST USED EXTENSION: {_session_state.get('last_app')}" if _session_state.get("last_app") else ""
        try:
            llm_app_ids, intent_type, _llm_lang = await _route_with_llm(message, catalog, history, user_id=user_info.get("id", ""), allowed_apps=_user_allowed_apps, session_hint=_session_hint_str, routing_context=_routing_context)
        except Exception as _routing_err:
            log.error(f"Hub routing LLM unavailable: {_routing_err}")
            return {"response": "**AI model is currently unavailable.** Check your LLM provider settings or enable platform fallback in Settings > AI Provider.", "_error": True, "_message_type": "navigate"}
        # LLM-detected language is authoritative (Haiku understands ALL languages)
        if _llm_lang and len(_llm_lang) == 2:
            context["_user_language"] = _llm_lang
            context["_user_language_name"] = _LANG_NAMES.get(_llm_lang, _llm_lang.upper())
            kctx.language = _llm_lang
            kctx.language_name = _LANG_NAMES.get(_llm_lang, _llm_lang.upper())
            # Persist for future messages (ack/greetings skip LLM routing)
            try:
                _hr = await _get_hub_redis()
                await _hr.setex(f"imperal:user_lang:{user_info.get('id', '')}", 86400, _llm_lang)
            except Exception:
                pass
        if llm_app_ids:
            # LLM routing succeeded — use as PRIMARY, override embedding candidates
            llm_extensions = {}
            for app_id in llm_app_ids:
                if app_id in all_extensions:
                    llm_extensions[app_id] = all_extensions[app_id]
                    llm_extensions[app_id]["relevance"] = 0.9
                else:
                    for t in catalog.tools:
                        if t.get("app_id") == app_id:
                            llm_extensions[app_id] = {**t, "relevance": 0.9}
                            break
            if llm_extensions:
                all_extensions = llm_extensions
                log.info(f"Hub LLM routing PRIMARY: {list(all_extensions.keys())} (intent={intent_type})")
        else:
            # LLM routing returned "none" or empty
            # Before navigating: check if this could be a management follow-up
            # (e.g. "включи обратно" after admin suspended an extension)
            _mgmt_keywords = ("enable", "disable", "activate", "suspend", "включи", "выключи",
                              "верни", "обратно", "turn on", "turn off")
            _msg_lower = message.lower()
            _is_mgmt_followup = any(kw in _msg_lower for kw in _mgmt_keywords)
            
            if _is_mgmt_followup and ("admin" in _user_allowed_apps):
                # Route to admin as management fallback
                for t in catalog.tools:
                    if t.get("app_id") == "admin":
                        all_extensions = {"admin": {**t, "relevance": 0.9}}
                        intent_type = "write"
                        log.info(f"Hub: management fallback → admin (msg='{message[:50]}', max_emb_score={_max_score:.3f})")
                        break
                else:
                    log.info(f"Hub LLM routing: none → navigate (max_emb_score={_max_score:.3f})")
                    return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton, routing_context=_routing_context)
            else:
                log.info(f"Hub LLM routing: none → navigate (max_emb_score={_max_score:.3f})")
                return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton, routing_context=_routing_context)

    # Store intent_type in context for executor KAV verification
    context["_intent_type"] = intent_type
    kctx.intent_type = intent_type

    # RBAC filter: remove extensions the user doesn't have access to (per access_policy)
    if _user_allowed_apps is not None:
        all_extensions = {k: v for k, v in all_extensions.items() if k in _user_allowed_apps}

    # Select dispatch targets based on LLM routing result
    if is_automation and all_extensions:
        target = _detect_automation_target(message, all_extensions)
        if target and target in all_extensions:
            extensions = {target: all_extensions[target]}
        else:
            sorted_exts = sorted(all_extensions.items(), key=lambda x: x[1].get("relevance", 0), reverse=True)
            extensions = {sorted_exts[0][0]: sorted_exts[0][1]}
        log.info(f"Hub: automation action → {list(extensions.keys())} only")
    else:
        extensions = _select_dispatch_targets(all_extensions, message)

    log.info(f"Hub: message='{message[:60]}', discovered={len(found_tools)}, candidates={len(all_extensions)}, dispatching={list(extensions.keys())}, intent={intent_type}")

    # ── Kernel Context Enrichment — inject session state for follow-ups ──
    user_id = user_info.get("id", "")
    enriched_message = await _enrich_if_followup(message, user_id)

    # No matches even after LLM routing — session state fallback for follow-ups
    if not extensions:
        session_state = await _load_session_state(user_id)
        if session_state and session_state.get("last_app") and catalog and catalog.loaded:
            last_app = session_state["last_app"]
            # Try last_app first — but ONLY if user has access (RBAC check)
            if last_app in _user_allowed_apps:
                for t in catalog.tools:
                    if t.get("app_id") == last_app:
                        extensions = {last_app: {**t, "relevance": 0.8}}
                        log.info(f"Hub session fallback: -> last_app={last_app}")
                        break
            # last_app not accessible -> admin fallback (only if user has access)
            if not extensions:
                if "admin" in _user_allowed_apps:
                    for t in catalog.tools:
                        if t.get("app_id") == "admin":
                            extensions = {"admin": {**t, "relevance": 0.8}}
                            log.info(f"Hub session fallback: last_app={last_app} unavailable -> admin")
                            break

    if not extensions:
        return await _hub_navigate(message, history, user_info, catalog, _user_allowed_apps, context=context, skeleton=skeleton, routing_context=_routing_context)

    # Single extension — fast path with auto-reroute
    if len(extensions) == 1:
        app_id, candidate = next(iter(extensions.items()))
        # Hub ALWAYS waits for full result — no sub-extension promotion.
        # Outer hub_chat is already inline (300s timeout from session_workflow).
        result = await _dispatch_one(kctx, app_id, candidate["activity_name"],
                                     enriched_message, history, skeleton, context,
                                     suppress_promotion=True,
                                     confirmation_bypassed=context.get("_confirmation_bypassed", False))
        # Passthrough: confirmation goes to session_workflow (task_promoted should NOT happen now)
        if _is_passthrough(result):
            log.info(f"Hub passthrough: {result.get('type')} from {app_id}")
            return result
        # Extract response text + truth flags from dispatch result
        _truth_flags = {}
        if isinstance(result, dict) and "response" in result:
            _truth_flags = {k: v for k, v in result.items() if k.startswith("_had_")}
            result_text = _strip_kernel_context(result.get("response", str(result)))
            log.info(f"Hub single dispatch result: app={app_id} _had_fn={result.get('_had_function_calls')} _had_action={result.get('_had_successful_action')} _handled={result.get('_handled')} truth_flags={_truth_flags}")
        elif isinstance(result, str):
            result_text = result
        else:
            result_text = str(result)

        # Check: extension didn't call any functions OR returned error
        _was_handled = True
        if isinstance(result, dict):
            _was_handled = result.get("_handled", True)

        if not _was_handled or _is_extension_error(result_text if isinstance(result_text, str) else str(result)):
            log.info(f"Hub: {app_id} not handled (_handled={_was_handled}), trying fallbacks")
            # Try other extensions from all_extensions
            for fallback_app, fallback_candidate in all_extensions.items():
                if fallback_app != app_id:
                    fb_result = await _dispatch_one(
                        kctx, fallback_app, fallback_candidate["activity_name"],
                        message, history, skeleton, context,
                        suppress_promotion=True,
                        confirmation_bypassed=context.get("_confirmation_bypassed", False))
                    if _is_passthrough(fb_result):
                        return fb_result
                    fb_handled = True
                    fb_flags = {}
                    if isinstance(fb_result, dict):
                        fb_handled = fb_result.get("_handled", True)
                        fb_flags = {k: v for k, v in fb_result.items() if k.startswith("_had_")}
                        fb_text = fb_result.get("response", str(fb_result))
                    else:
                        fb_text = str(fb_result)
                    if fb_handled and not _is_extension_error(fb_text):
                        _fb_result = {"response": fb_text, **fb_flags}
                        if isinstance(fb_result, dict) and fb_result.get("_action_meta"):
                            _fb_result["_action_meta"] = fb_result["_action_meta"]
                        if isinstance(fb_result, dict) and fb_result.get("_functions_called"):
                            _fb_result["_functions_called"] = fb_result["_functions_called"]
                        if fb_flags.get("_had_function_calls"):
                            _fb_result["_message_type"] = "function_call"
                        return _fb_result
            # All fallbacks failed — KERNEL GUARD: honest error, NEVER fabricate
            # Routing identified extensions but ALL dispatch attempts failed.
            # Navigate would hallucinate the action ("Creating note...") without executing.
            log.warning(f"Hub: ALL dispatches failed for '{message[:50]}' — returning honest error (no navigate)")
            _err_lang = getattr(kctx, 'language', '') if kctx else ''
            if _err_lang == 'ru':
                _err_msg = "Не удалось выполнить действие. Пожалуйста, попробуйте ещё раз."
            else:
                _err_msg = "Could not complete the action. Please try again."
            return {"response": _err_msg, "_handled": False}
        await _save_session_state(user_id, app_id, result if isinstance(result, dict) else {"response": result_text})
        _result = {"response": result_text, **_truth_flags}
        if isinstance(result, dict) and result.get("_action_meta"):
            _result["_action_meta"] = result["_action_meta"]
        if isinstance(result, dict) and result.get("_functions_called"):
            _result["_functions_called"] = result["_functions_called"]
        # Set message type for delivery label
        if _truth_flags.get("_had_function_calls"):
            _result["_message_type"] = "function_call"
        return _result

    # ── Step 2: CHAIN EXECUTION ──────────────────────────────────
    # Single LLM call plans ordered steps with per-step messages.
    # Same extension CAN appear multiple times (e.g. gmail read → notes → gmail send).
    chain_steps = await _plan_chain_steps(enriched_message, list(extensions.keys()), user_id=user_info.get("id", ""))
    _chain_fc = []  # Collect _functions_called from all chain steps
    _chain_meta = None  # Last step's _action_meta
    
    # Create persistent chain task for System Tray (NO task.promoted SSE — no chat card)
    _chain_task_id = None
    try:
        from imperal_sdk.runtime.task_manager import generate_task_id, create_task, update_progress, complete_task, promote_task
        _chain_redis = await _get_hub_redis()
        _chain_task_id = generate_task_id()
        await create_task(_chain_redis, _chain_task_id, user_id, "default",
                          "__system__", "chain", message[:200], threshold_ms=0)
        await promote_task(_chain_redis, _chain_task_id)  # visible=True for tray
        # Publish SSE for SystemMonitor real-time updates (ChatClient doesn't listen to scope 'task')
        try:
            await _chain_redis.publish("imperal:events:default", json.dumps({
                "type": "state_changed", "scope": "task", "action": "promoted",
                "data": {"task_id": _chain_task_id, "message_preview": message[:200],
                         "app_id": "__system__", "tool_name": "chain", "user_id": user_id}
            }))
        except Exception:
            pass
        log.info(f"Hub chain: tray task {_chain_task_id} for {len(chain_steps)} steps")
    except Exception as _ct_err:
        log.warning(f"Hub chain: tray task failed: {_ct_err}")

    successful = []  # list of (app_id, result_str) — preserves order + duplicates
    _truth_flags = {}
    
    _chain_total = len(chain_steps)
    for _chain_idx, (app_id, step_message) in enumerate(chain_steps):
        if app_id not in extensions:
            continue
        candidate = extensions[app_id]

        # Update status between chain steps so frontend knows we are alive
        _step_label = f"Step {_chain_idx + 1}/{_chain_total}: {step_message[:60]}..."
        await _update_chain_status(user_id, context, _step_label)
        if _chain_task_id:
            try:
                _pct = int((_chain_idx / _chain_total) * 100)
                await update_progress(_chain_redis, _chain_task_id, _pct, _step_label)
                await _chain_redis.publish("imperal:events:default", json.dumps({
                    "type": "state_changed", "scope": "task", "action": "progress",
                    "data": {"task_id": _chain_task_id, "percent": _pct,
                             "progress_message": _step_label, "user_id": user_id}
                }))
            except Exception:
                pass

        _chain_ctx = _build_chain_step_context(_chain_idx, successful)
        enriched_msg = f"{_chain_ctx}\n\n{step_message}" if _chain_ctx else step_message
        
        # Suppress task promotion in chain mode — we need all results for combine.
        # Chain mode: don't set _intent_type from keywords — they break non-EN/RU languages.
        # The function's @chat.function(action_type=...) is the source of truth.
        # ChatExtension reads action_type from the decorator, not from Hub intent.
        context["_intent_type"] = "chain"  # Special value: bypasses intent guard in extension
        kctx.intent_type = "chain"
        result = await _dispatch_one(
            kctx, app_id, candidate["activity_name"],
            enriched_msg, history, skeleton, context,
            chain_mode=True, suppress_promotion=True,
            confirmation_bypassed=context.get("_confirmation_bypassed", False),
        )
        
        # confirmation / task_limit_reached — must stop chain
        if _is_passthrough(result):
            log.info(f"Hub chain passthrough: {result.get('type')} from {app_id}")
            return result
        
        if isinstance(result, dict) and "response" in result:
            result_str = result["response"]
        else:
            result_str = str(result)
        if isinstance(result, Exception):
            log.info(f"Hub chain: {app_id} step {_chain_idx+1} raised exception, skipping")
            continue
        
        _chain_handled = True
        if isinstance(result, dict):
            _chain_handled = result.get("_handled", True)
        refused = not _chain_handled or _is_extension_error(result_str)
        if refused:
            log.info(f"Hub chain: {app_id} step {_chain_idx+1} refused, continuing")
            continue
        
        # Collect truth flags + verification data from chain steps
        if isinstance(result, dict) and result.get("_had_function_calls"):
            _truth_flags["_had_function_calls"] = True
        if isinstance(result, dict) and result.get("_had_successful_action"):
            _truth_flags["_had_successful_action"] = True
        if isinstance(result, dict) and result.get("_functions_called"):
            _chain_fc.extend(result["_functions_called"])
        if isinstance(result, dict) and result.get("_action_meta"):
            _chain_meta = result["_action_meta"]
        successful.append((app_id, result_str))
        log.info(f"Hub chain: {app_id} step {_chain_idx+1} done, passing context to next")
    
    if not successful:
        # KERNEL GUARD: Anti-fabrication — chain dispatch attempted but ALL steps failed
        log.warning(f"Hub: ALL chain steps failed for '{message[:50]}' — returning honest error (no navigate)")
        _err_lang = getattr(kctx, 'language', '') if kctx else ''
        if _err_lang == 'ru':
            _err_msg = "Не удалось выполнить действие. Пожалуйста, попробуйте ещё раз."
        else:
            _err_msg = "Could not complete the action. Please try again."
        return {"response": _err_msg, "_handled": False}

    _last_app, _last_result = successful[-1]
    await _save_session_state(user_id, _last_app, {"response": _last_result})

    await _update_chain_status(user_id, context, "Combining results...")

    # __ Step 3: COMBINE ───────────────────────────────────────────
    # Convert list to dict for combine (merge duplicate app results)
    _combine_dict = {}
    for _s_idx, (_s_app, _s_result) in enumerate(successful):
        _key = f"{_s_app}" if _s_app not in _combine_dict else f"{_s_app} (step {_s_idx+1})"
        _combine_dict[_key] = _s_result
    combined = await _hub_combine(message, _combine_dict, user_info)
    combined.update(_truth_flags)
    if _chain_fc:
        combined["_functions_called"] = _chain_fc
    if _chain_meta:
        combined["_action_meta"] = _chain_meta

    # Complete chain tray task
    if _chain_task_id:
        try:
            await complete_task(_chain_redis, _chain_task_id, user_id, "completed")
            await _chain_redis.publish("imperal:events:default", json.dumps({
                "type": "state_changed", "scope": "task", "action": "completed",
                "data": {"task_id": _chain_task_id, "user_id": user_id}
            }))
        except Exception:
            pass
    # Set message type: function_call if any step called functions, else response
    if _truth_flags.get("_had_function_calls"):
        combined["_message_type"] = "function_call"
    return combined

