# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
from __future__ import annotations
from dataclasses import dataclass
import httpx


@dataclass
class CompletionResult:
    text: str
    tokens_used: int = 0
    model: str = ""


class AIClient:
    """AI completion client. Usage auto-metered by platform."""

    def __init__(self, gateway_url: str, auth_token: str, extension_id: str):
        self._gateway_url = gateway_url.rstrip("/")
        self._auth_token = auth_token
        self._extension_id = extension_id

    async def complete(self, prompt: str, model: str = "claude-sonnet", **kwargs) -> CompletionResult:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self._gateway_url}/v1/internal/ai/complete", json={"prompt": prompt, "model": model, "extension_id": self._extension_id, **kwargs}, headers={"Authorization": f"Bearer {self._auth_token}"}, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return CompletionResult(text=data.get("text", ""), tokens_used=data.get("tokens_used", 0), model=data.get("model", model))
