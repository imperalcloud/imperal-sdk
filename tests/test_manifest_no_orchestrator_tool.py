"""Federal I-MANIFEST-NO-ORCHESTRATOR-TOOL — emitter must not produce tool_*_chat."""
import re
import warnings
from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension


def test_chat_extension_does_not_emit_orchestrator_tool():
    """Building a manifest from an ext with a ChatExtension must not include tool_<name>_chat."""
    ext = Extension(app_id="demo", description="demo ext for emitter test")
    chat = ChatExtension(ext, tool_name="demo_legacy_kwarg", description="legacy")

    @chat.function(name="list_items", description="list user items for the demo ext")
    async def list_items(ctx):
        return {"items": []}

    # Build the manifest. Discover the right entry point — try common names:
    manifest = None
    try:
        from imperal_sdk.manifest import emit_manifest
        manifest = emit_manifest(ext)
    except (ImportError, AttributeError):
        try:
            from imperal_sdk.manifest import build_manifest
            manifest = build_manifest(ext)
        except (ImportError, AttributeError):
            try:
                from imperal_sdk.manifest import generate_manifest
                manifest = generate_manifest(ext)
            except (ImportError, AttributeError):
                # Try via Extension method:
                manifest = ext.to_manifest() if hasattr(ext, "to_manifest") else ext.build_manifest()

    assert manifest is not None, "could not locate manifest emitter entry point"
    if hasattr(manifest, "dict"):
        manifest = manifest.dict()
    elif hasattr(manifest, "model_dump"):
        manifest = manifest.model_dump()

    tool_names = [t.get("name") if isinstance(t, dict) else getattr(t, "name", "")
                  for t in (manifest.get("tools") or [])]
    pattern = re.compile(r"^tool_.+_chat$")
    legacy_entries = [n for n in tool_names if pattern.match(n)]
    assert legacy_entries == [], (
        f"emitter MUST NOT produce tool_*_chat entries; got {legacy_entries}"
    )
    # The actual @chat.function handlers ARE expected:
    assert "list_items" in tool_names, (
        f"@chat.function handlers must still be emitted; tools were {tool_names}"
    )


def test_chat_extension_tool_name_kwarg_does_not_warn():
    """ChatExtension(tool_name=...) is the canonical chat-registration key — it
    must NOT emit a DeprecationWarning.

    Reversed from the transient SDK 5.0.0 stance: the kwarg is load-bearing
    (manifest grouping key + per-turn prompt + scope guards), has no
    replacement API, and every first-party extension passes it. A deprecation
    warning with no migration path is cry-wolf noise, so it was removed.
    """
    ext = Extension(app_id="demo2", description="demo ext for deprecation test")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ChatExtension(ext, tool_name="legacy_name", description="legacy")
    tool_name_deprecations = [
        w for w in caught
        if issubclass(w.category, DeprecationWarning) and "tool_name" in str(w.message)
    ]
    assert not tool_name_deprecations, (
        "ChatExtension(tool_name=...) must NOT emit a tool_name DeprecationWarning; "
        f"got: {[str(w.message) for w in tool_name_deprecations]}"
    )


def test_chat_extension_tool_name_optional_defaults_to_app_id():
    """tool_name is optional — when omitted it derives from the extension app_id
    (``tool_<app_id>_chat``) and is used as the manifest registration key."""
    ext = Extension(app_id="demo3", description="demo ext for default-tool-name test")
    chat = ChatExtension(ext, description="no explicit tool_name")
    assert chat.tool_name == "tool_demo3_chat", (
        f"omitted tool_name must default to tool_<app_id>_chat; got {chat.tool_name!r}"
    )
    assert "tool_demo3_chat" in ext._chat_extensions, (
        "default tool_name must be registered as the _chat_extensions key"
    )
