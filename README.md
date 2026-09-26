<div align="center">

# 🐝 Imperal Quantum SDK (`imperal-sdk`)

### The Official Foundation AI Cloud OS Framework for Imperal Cloud & Webbee 🐝

**Write autonomous, context-aware AI tools and extensions in pure, idiomatic Python. Zero manifests. 0 lines of JSON boilerplate. Automatic reactive UI synthesis. Ambient cloud context. Multi-surface liquid morphing across Terminal, Web Panel, Telegram, and Voice. Python 3.6 to 3.14+ universal support.**

[![PyPI](https://img.shields.io/pypi/v/imperal-sdk?color=FFB800&label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/badge/python-3.6%20--%203.14%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/imperal-sdk/)
[![Protocol](https://img.shields.io/badge/protocol-ICNLI%20v6.0%20Quantum-00D2FF?style=flat-square)](https://icnli.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1629%20passed%20%7C%20100%25-success?style=flat-square)]()
[![DX](https://img.shields.io/badge/DX-Zero--Boilerplate%20%E2%9A%A1-orange?style=flat-square)]()

[Documentation](https://docs.imperal.io) · [ICNLI Protocol Spec](https://icnli.org) · [Imperal Cloud Panel](https://panel.imperal.io) · [Marketplace](https://panel.imperal.io/marketplace)

</div>

---

## 🌌 The Quantum Leap: Forget Legacy AI Agent Tooling

In early AI agent frameworks and Web2 SDKs, building tools for agents degenerated into bureaucratic overhead:
- ❌ **Manifest Hell**: Manually maintaining hundreds of lines of fragile `manifest.json` files.
- ❌ **Redundant Schema Declarations**: Copy-pasting parameters between Python signatures and JSON Schema definitions.
- ❌ **Frontend Tax**: Needing dedicated UI engineers just to render an agent's structured response in a web dashboard.
- ❌ **Surface Fragmentation**: What worked in the terminal broke in Telegram and looked horrible on the web.
- ❌ **Prompt Token Waste**: Leaking internal runtime parameters (`context`, `user_id`, `tokens`) directly into LLM function-calling schemas.

### ⚡ Enter ICNLI Quantum SDK v6.0

**Imperal Quantum SDK** delivers to autonomous cloud agents what **FastAPI** brought to modern web APIs — elevating cloud application development into an ultra-clean, quantum plane:

1. 🚀 **Zero-Manifest (0 Lines of JSON)**: Manifest definitions, parameter schemas, docstrings for LLM planning, RBAC security scopes, and billing tiers are extracted dynamically from standard Python function signatures and type hints.
2. 🎨 **Auto-IR (UI-as-Data)**: Simply return standard Python dictionaries, dataclasses, or lists. The Imperal Cloud runtime automatically projects them into reactive Declarative UI components (cards, metric grids, data tables) without writing a single line of CSS or frontend code.
3. 🔮 **Ambient Context Injection**: Seamlessly access session identity (`Context`), encrypted key-value storage (`Store`), persistent object storage (`Storage`), and the native AI engine (`AI`) without polluting the LLM's function calling schema.
4. 🔀 **Liquid Multi-Surface Morphing**: One codebase transparently adapts its presentation across **Terminal TUI** (Webbee Code), **Web Console** (Imperal Panel), **Telegram Messenger**, and **Ambient Voice**.
5. 🛡️ **Universal Python Compatibility (3.6 – 3.14+)**: From legacy MCP environments running Python 3.6 up to cutting-edge Python 3.14 runtimes, the core SDK operates with 100% backward compatibility and zero overhead.
6. 💎 **100% Backward Compatible**: Full support for classic enterprise extensions built on `imperal_sdk.Extension` (validated by 1,620+ automated tests).

---

## 🚀 Quickstart in 60 Seconds

### 1. Installation

```bash
pip install imperal-sdk
```

### 2. Your First Cloud App in 15 Lines (`server_pulse.py`)

```python
from imperal_sdk import App, Context

# Instantiate your Quantum App — your manifest is already generated!
app = App("server-pulse", name="Server Pulse", category="devops")

@app.tool(pricing=5, destructive=False)
def check_host(host: str, port: int = 443, ctx: Context = None) -> dict:
    """Check server availability and SSL certificate expiration in real time."""
    # Pure Python business logic:
    is_online = True
    ssl_days = 89

    # Return pure data — Imperal Cloud synthesizes the reactive UI on the fly!
    return {
        "status": "online" if is_online else "down",
        "host": host,
        "ssl_days": ssl_days,
        "metric": f"{ssl_days} days left"
    }
```

### What happened under the hood?
- ✅ **Valid ICNLI Manifest v6.0**: Automatically synthesized with zero JSON.
- ✅ **Type-to-Schema Translation**: `host` and `port` became typed JSON Schema properties with defaults.
- ✅ **Docstring Extraction**: The docstring was converted into the LLM classifier and planner description.
- ✅ **Security Scopes**: Granular RBAC scope `server-pulse:check_host` was registered automatically.
- ✅ **Ambient Context**: `ctx` was hidden from the LLM prompt while remaining injected at execution time.
- ✅ **Auto-IR Projection**: The returned dictionary automatically renders in `panel.imperal.io` as a styled **Metric Card** with badges and metrics!

---

## 💎 Core Quantum Superpowers

### 1. ⚡ Automatic Schema Synthesis (Type-to-Schema Engine)

Write clean, idiomatic Python with standard typing. The SDK extracts complete JSON Schema definitions:

```python
from typing import List, Optional

@app.tool()
async def deploy_services(
    environment: str,
    replicas: int = 3,
    tags: Optional[List[str]] = None,
    dry_run: bool = False
) -> dict:
    """Deploy microservice instances to the specified cluster zone with autoscaling."""
    ...
```

Synthesized parameter schema:
```json
{
  "name": "deploy_services",
  "description": "Deploy microservice instances to the specified cluster zone with autoscaling.",
  "parameters": {
    "type": "object",
    "properties": {
      "environment": { "type": "string" },
      "replicas": { "type": "integer", "default": 3 },
      "tags": { "type": "array", "items": { "type": "string" } },
      "dry_run": { "type": "boolean", "default": false }
    },
    "required": ["environment"]
  }
}
```

---

### 2. 🎨 Auto-IR: UI-as-Data (Frontend without Frontend Code)

The Imperal Cloud Kernel inspects your return payloads and projects them into Declarative UI:

| Python Return Value | Rendered Appearance in Imperal Panel |
| :--- | :--- |
| `{"status": "ok", "metric": "99.98%", ...}` | 🎴 **Metric Card**: Interactive card with status badge, headline metric, and details |
| `[{"id": 1, "name": "node-a", "cpu": 14}, ...]` | 📊 **Data Table**: Sortable, responsive table with auto-detected columns |
| `{"_ui": {"type": "custom", ...}}` | 🧩 **Declarative IR**: Full customization using Imperal UI Kit primitives |

---

### 3. 🔮 Ambient Context: Invisible Access to the Entire Cloud OS

The `ctx: Context` argument is hidden from the LLM schema (saving prompt tokens), but grants full platform access at runtime:

```python
@app.tool()
async def analyze_anomalies(cluster_id: str, ctx: Context = None) -> dict:
    # 1. Access high-speed key-value store (Redis):
    last_run = await ctx.store.get(f"scan:{cluster_id}")

    # 2. Query the native AI brain (LLM cascade):
    verdict = await ctx.ai.complete(f"Diagnose cluster status: {cluster_id}")

    # 3. Read authenticated identity and enterprise tenant boundaries:
    actor_email = ctx.user.email
    tenant_id = ctx.user.tenant_id

    return {
        "status": "analyzed",
        "verdict": verdict.text,
        "initiated_by": actor_email,
        "metric": "Clean"
    }
```

---

### 4. 🔀 Multi-Surface Liquid Morphing

Webbee operates natively across all surfaces. The same tool presentation is automatically morphed:
- **Terminal (Webbee Code TUI)**: High-density formatted output, ASCII tables, and numbered hotkey shortcuts (`[1] Execute`, `[2] Abort`).
- **Web Console (Imperal Panel)**: Interactive Declarative UI cards, modal dialogs, and real-time streaming widgets.
- **Telegram Messenger**: Concise mobile cards with inline button callbacks.
- **Ambient Voice**: Spoken concise executive summaries.

---

### 5. 🔗 Cross-Extension Unix Piping

Tools across completely different extensions can be piped together through plain language:
```text
"Webbee, fetch domains from DNS checker, pass them to SSL auditor, and ping me on Telegram if expiring soon."
```
Every tool declaring typed inputs and outputs participates in deterministic, automated pipeline chaining.

---

## 🧪 Hermetic Local Testing (Zero Network Required)

Imperal SDK includes a built-in autonomous mock suite (`imperal_sdk.testing.autonomous_mock`):

```python
import pytest
from imperal_sdk.testing.autonomous_mock import MockContext
from server_pulse import check_host

def test_check_host_locally():
    mock_ctx = MockContext(user_id="imp_u_test", role="admin")
    result = check_host(host="imperal.io", port=443, ctx=mock_ctx)

    assert result["status"] == "online"
    assert "_ui" in result
    assert result["_ui"]["type"] == "metric_card"
    assert result["_ui"]["badge"] == "online"
```

Run test suite:
```bash
pytest -v
```

---

## 🏗️ Imperal Cloud OS Architecture

```
                     ┌───────────────────────────────┐
                     │          Webbee Brain         │
                     │    (Agentic AI Reasoning)     │
                     └───────────────┬───────────────┘
                                     │ Intent & Tool Calls
                                     ▼
                     ┌───────────────────────────────┐
                     │    ICNLI Quantum SDK v6.0     │
                     │   imperal_sdk.App / Extension │
                     └───────────────┬───────────────┘
                                     │ Declarative IR & Telemetry
                ┌────────────────────┼────────────────────┐
                ▼                    ▼                    ▼
        ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
        │ Imperal Panel│     │  Webbee Code │     │   Telegram   │
        │   (Web UI)   │     │ (Terminal)   │     │  (Messenger) │
        └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 📜 Compatibility & Specifications

- **Python Runtime**: Universal support for **Python 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14+**.
- **Footprint**: Ultra-lightweight core with lazy attribute resolution (PEP 562 with Python 3.6 fallback). Sub-15ms cold start.
- **Standards**: 100% compliant with the [ICNLI Open Protocol](https://icnli.org) (CC BY-SA 4.0).
- **License**: [Apache-2.0](LICENSE).

---

<div align="center">

**Imperal Cloud — The World's First Decentralized ICNLI AI Cloud OS.**  
*Crafted with 💛 and 🐝 by Imperal, Valentin Scerbacov, and the open-source community.*

</div>
