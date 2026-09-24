<div align="center">

# Imperal SDK 🐝

### The Official Foundation OS SDK for Imperal Cloud — The World's First Decentralized ICNLI AI Cloud OS

**Build adaptive, context-aware extensions for Webbee 🐝. Write structured Python handlers that morph across every surface — Terminal, Web Panel, Telegram, and Ambient Voice.**

[![PyPI](https://img.shields.io/pypi/v/imperal-sdk?color=blue&label=PyPI)](https://pypi.org/project/imperal-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/imperal-sdk)](https://pypi.org/project/imperal-sdk/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![ICNLI Compliant](https://img.shields.io/badge/protocol-ICNLI%20v7-brightgreen)](https://icnli.org)
[![Tests](https://img.shields.io/badge/tests-1624%20passed%20%7C%20100%25-success)]()

[Documentation](https://docs.imperal.io) · [Quickstart](https://docs.imperal.io/en/getting-started/quick-start/) · [Marketplace](https://imperal.io/marketplace) · [Protocol Spec](https://icnli.org)

</div>

---

## 🌟 What is Imperal SDK?

**Imperal Cloud** is an AI Cloud OS built on the open **ICNLI protocol** (Infrastructure Contextual Natural Language Interface). It connects the core contexts of digital infrastructure — compute, storage, DNS, billing, databases, git repositories, and external APIs — into a unified, intent-driven nervous system.

**Webbee 🐝** is its native Agentic AI Brain. Rather than a fragile chatbot guessing unstructured commands, Webbee reasons over grounded code contracts, verifies intent through causal rails, and executes deterministic actions across distributed infrastructure.

**Imperal SDK (`imperal-sdk`)** is the official framework for developing, testing, and shipping extensions into this ecosystem.

```bash
pip install imperal-sdk
```

---

## ⚡ Architectural Superpowers

### 1. Liquid Dynamic UI (`imperal_sdk.ui`)
Forget static, rigid HTML pages. Declare the **semantic state of user intent** (`MorphingState`), available affordances, cognitive context, and urgency. Imperal's multi-surface projector adapts the UI on the fly:
- **Terminal (Webbee Code TUI):** Compact, numbered keyboard shortcuts (`[1] Reboot`, `[2] Inspect`).
- **Web Console (Imperal Panel):** Rich interactive cards, topological graphs, and metric badges.
- **Mobile / Telegram:** Urgent glanceable action cards with one-tap inline buttons.
- **Ambient / Voice:** Spoken essence with hands-free verbal consent confirmation.

### 2. Situational Awareness (`ctx.surface`)
Every tool handler knows its execution modality in real time via `ctx.surface` (`"terminal"`, `"panel"`, `"telegram"`, `"ambient"`). Extensions adapt their responses, output verbosity, and action flows dynamically to the user's active context.

### 3. Sync & Async Parity (Dual-Engine Execution)
Write plain synchronous functions or high-concurrency `async` coroutines. The SDK's dispatcher introspects handlers on registration and automatically delegates sync operations to dedicated worker threadpools without blocking the platform's async event loop.

### 4. Zero-Dependency Core Primitives (`imperal_sdk.core`)
Ultra-lightweight stdlib primitives (`CancellationToken`, `StreamEmitter`, `SchemaValidator`, `ICNLIComponent`) runnable anywhere — from embedded edge appliances to distributed cloud workers — without pulling heavy dependencies.

### 5. Autonomous Local Mocking Kit (`imperal_sdk.testing`)
Spin up comprehensive, zero-network unit and E2E integration tests in milliseconds with embedded mocks for Billing, RBAC, AI Completion, Store, and Storage.

### 6. Intelligent DX & CLI (`imperal sdk init` & `validate --fix`)
Scaffold enterprise-ready extension packages and lint manifests against federal invariant contracts with automated autofixing (`--fix`).

---

## 🚀 60-Second Quickstart

Create an adaptive extension with typed inputs, situational awareness, and liquid UI in seconds:

```python
from imperal_sdk import Extension, ChatExtension, ActionResult
from imperal_sdk.ui import MorphingState, Affordance, CognitiveContext
from pydantic import BaseModel, Field

ext = Extension(
    "cluster-sentinel",
    version="1.0.0",
    display_name="Cluster Sentinel",
    description="Monitors and remediates distributed cluster incidents.",
    icon="icon.svg",
    actions_explicit=True,
)

chat = ChatExtension(ext, tool_name="cluster_sentinel", description="Cluster health remediation.")


class RemediateParams(BaseModel):
    node_id: str = Field(..., description="Target node identifier, e.g. 'us-east-1a'")
    force: bool = Field(False, description="Bypass soft draining")


@chat.function("remediate_node", description="Remediate an unstable node.", action_type="destructive")
async def remediate_node(ctx, params: RemediateParams) -> ActionResult:
    # Build intent state that morphs across surfaces on the fly
    state = MorphingState(
        context="node_split_brain",
        summary=f"Node {params.node_id} replication lag critical",
        urgency="critical",
        risk="destructive",
        affected_entities=[params.node_id],
        metrics={"replication_lag_s": 84.2, "pending_wal_mb": 1420},
        affordances=[
            Affordance(id="restart", label="Restart Daemon", risk="write", primary=True, shortcut="r"),
            Affordance(id="isolate", label="Isolate Node", risk="destructive", requires_confirmation=True, shortcut="i"),
        ],
        cognitive=CognitiveContext(situation="incident_response", urgency="critical"),
    )

    # Return as an adaptive liquid morph
    return ActionResult.morph(
        state,
        data={"node_id": params.node_id, "status": "action_required"},
        summary=f"Remediation plan ready for {params.node_id}",
    )
```

---

## 🛠️ CLI Tooling

The SDK includes the official `imperal` CLI for development workflows:

```bash
# Scaffold a new extension project
imperal sdk init my-extension

# Validate manifest and schema against federal contracts
imperal sdk validate .

# Automatically fix manifest issues and inject safe defaults
imperal sdk validate . --fix

# Deploy directly to your connected Imperal Cloud instance
imperal deploy .
```

---

## 🧪 Testing Without Network or Servers

Run local deterministic tests without cloud dependencies:

```python
import pytest
from imperal_sdk.testing import AutonomousMockEnv
from imperal_sdk.types.action_result import ActionResult

@pytest.mark.asyncio
async def test_remediate_node_offline():
    env = AutonomousMockEnv()
    ctx = env.create_context(
        user_id="imp_u_admin",
        role="admin",
        surface="terminal",  # Test terminal TUI projection
    )

    result = await remediate_node(ctx, RemediateParams(node_id="node-42"))
    assert result.status == "success"
    
    # Verify surface projection
    projection = result.ui.project_for_surface(ctx.surface)
    assert projection["surface"] == "terminal"
    assert "[1] Restart Daemon (r)" in projection["shortcuts"][0]
```

---

## 📦 What Can You Build?

| Extension Component | Capabilities |
|---|---|
| **Chat Tools (`@chat.function`)** | Structured typed handlers callable by Webbee from natural language with automatic validation. |
| **Liquid UI (`ActionResult.morph`)** | Adaptive intent interfaces morphing between Terminal TUI, Panel Cards, and Telegram Buttons. |
| **Declarative Panels (`@ext.panel`)** | Interactive dashboards and administration consoles rendered inside Imperal Panel. |
| **Skeletons (`@ext.skeleton`)** | High-efficiency state feeds providing real-time ambient awareness to Webbee's reasoning loop. |
| **Scheduled Jobs (`@ext.schedule`)** | Reliable background jobs executed by distributed Temporal workflows. |
| **Webhook Ingestors (`@ext.webhook`)** | Inbound HTTP event processors with automatic HMAC cryptographic verification. |

---

## 📜 Specifications & Compliance

Imperal SDK strictly enforces the **Federal Invariant Architecture (ICNLI v7)**:
- **Zero Hallucination:** Strict parameter type casting and schema enforcement via Pydantic v2.
- **Reversible Operations:** Support for transactional receipts (`ActionResult.undo` and `ActionResult.diff`).
- **Security-First Tenancy:** Explicit actor context (`ctx.user`, `ctx.tenant`, `ctx.rbac`) with boundary isolation.
- **Auditable Intent:** Every state transition is recorded in the immutable infrastructure ledger.

---

## 📚 Community & Resources

- 📖 **Documentation:** [docs.imperal.io](https://docs.imperal.io)
- 🚀 **Marketplace:** [imperal.io/marketplace](https://imperal.io/marketplace)
- 🐝 **Imperal Cloud Platform:** [imperal.io](https://imperal.io)
- ⚖️ **License:** Apache 2.0

<div align="center">
<sub>Built with 💜 by Valentin Scerbacov and the Imperal Cloud Team. Powered by ICNLI.</sub>
</div>
