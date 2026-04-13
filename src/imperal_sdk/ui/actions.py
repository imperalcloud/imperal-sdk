"""Imperal SDK · UI Actions."""
from __future__ import annotations

from .base import UIAction


def Call(function: str, **params) -> UIAction:
    """Direct function call — bypasses chat, executes @chat.function directly."""
    return UIAction(action="call", params={"function": function, "params": params})


def Navigate(path: str) -> UIAction:
    """Client-side navigation."""
    return UIAction(action="navigate", params={"path": path})


def Send(message: str) -> UIAction:
    """Send a message to chat."""
    return UIAction(action="send", params={"message": message})


def Open(url: str) -> UIAction:
    """Open URL in new browser tab."""
    return UIAction(action="open", params={"url": url})
