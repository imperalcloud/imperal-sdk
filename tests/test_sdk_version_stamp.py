"""Verify manifest emitter stamps current SDK version."""
import warnings
from imperal_sdk import Extension, __version__
from imperal_sdk.chat import ChatExtension
from imperal_sdk.manifest import generate_manifest


def test_emitted_manifest_has_current_sdk_version():
    ext = Extension(app_id="sdk_ver_test", description="version stamp test")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        chat = ChatExtension(ext, tool_name="legacy", description="legacy")

    @chat.function(name="ping", description="ping handler for the sdk_version stamp test")
    async def ping(ctx):
        return {"ok": True}

    manifest = generate_manifest(ext)
    if hasattr(manifest, "model_dump"):
        manifest = manifest.model_dump()
    assert manifest.get("sdk_version") == __version__, (
        f"emitted sdk_version must equal {__version__}, got {manifest.get('sdk_version')!r}"
    )
    assert __version__ == "5.0.1", f"SDK version should be 5.0.1; got {__version__}"
