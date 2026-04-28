"""Tests for ChatExtension(model=...) deprecation (Sprint 2).

After Sprint 2:
- model default → None (was "claude-haiku-4-5-20251001")
- self.model defaults to "" when no model= passed
- WARN-once class-level fires when model explicitly passed
"""
import logging
import pytest

from imperal_sdk import Extension
from imperal_sdk.chat import ChatExtension


@pytest.fixture(autouse=True)
def reset_warned_flag():
    """Reset class-level warn-once flag between tests for isolation."""
    if hasattr(ChatExtension, "_model_deprecation_warned"):
        delattr(ChatExtension, "_model_deprecation_warned")
    yield
    if hasattr(ChatExtension, "_model_deprecation_warned"):
        delattr(ChatExtension, "_model_deprecation_warned")


def test_chat_extension_no_model_default_is_empty():
    """ChatExtension(...) without model= → chat_ext.model is empty string."""
    ext = Extension("test-ext", version="1.0.0")
    chat_ext = ChatExtension(ext=ext, tool_name="t1", description="d1")
    assert chat_ext.model == "", (
        f"expected empty model when omitted; got {chat_ext.model!r}"
    )


def test_chat_extension_passing_model_warns_once(caplog):
    """Two ChatExtension(model=) calls → exactly 1 DEPRECATION warn."""
    ext1 = Extension("test1", version="1.0.0")
    ext2 = Extension("test2", version="1.0.0")
    with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.extension"):
        ChatExtension(ext=ext1, tool_name="t1", description="d1", model="x")
        ChatExtension(ext=ext2, tool_name="t2", description="d2", model="y")

    deprecation_warns = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "deprecated" in r.message.lower()
    ]
    assert len(deprecation_warns) == 1, (
        f"expected 1 DEPRECATION warn (class-level once); got {len(deprecation_warns)}"
    )


def test_chat_extension_no_warn_when_model_omitted(caplog):
    """ChatExtension(...) without model= MUST NOT trigger DEPRECATION."""
    ext = Extension("test-ext", version="1.0.0")
    with caplog.at_level(logging.WARNING, logger="imperal_sdk.chat.extension"):
        ChatExtension(ext=ext, tool_name="t1", description="d1")

    deprecation_warns = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "deprecated" in r.message.lower()
    ]
    assert len(deprecation_warns) == 0
