"""Federal I-MANIFEST-NO-ORCHESTRATOR-TOOL — emitter must not produce tool_*_chat."""
import re
import warnings
from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension


def test_chat_extension_does_not_emit_orchestrator_tool():
    """Building a manifest from an ext with a ChatExtension must not include tool_<name>_chat."""
    ext = Extension(app_id="demo", description="demo ext for emitter test")
    # Suppress the DeprecationWarning emitted by ChatExtension(tool_name=...) — covered separately.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
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


def test_chat_extension_tool_name_kwarg_emits_deprecation_warning():
    """ChatExtension(tool_name=...) must emit DeprecationWarning at construction."""
    ext = Extension(app_id="demo2", description="demo ext for deprecation test")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ChatExtension(ext, tool_name="legacy_name", description="legacy")
    deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecation, (
        "ChatExtension(tool_name=...) MUST emit a DeprecationWarning in SDK 5.0.0"
    )
    msg = str(deprecation[0].message)
    assert "tool_name" in msg and ("5.0.0" in msg or "5.1.0" in msg), (
        f"DeprecationWarning message must reference tool_name and version cutoff; got: {msg}"
    )
