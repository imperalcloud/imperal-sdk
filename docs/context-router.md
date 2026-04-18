# Context Router

> **DEPRECATED (2026-04-03):** The domain-based Context Router described in this document has been superseded by the **Tool Discovery Engine**. See `icnli-platform-core/tool-discovery-engine.md` for the current system. The `message_router.py` activity is DEPRECATED and no longer used in production. This document is preserved as a reference for the historical domain classification approach.

---

> How Imperal Cloud intelligently selects relevant tools for each user message using LLM-powered domain classification.

## Overview

The Context Router is a lightweight LLM pre-router that sits between the user's message and the main AI assistant. Its job is to classify each message into one or more **domains**, then filter the tool list so the assistant only sees tools relevant to the current request. This reduces prompt size, improves response accuracy, and lowers token costs.

Without routing, an extension with 50 tools across 10 domains would include all 50 tool definitions in every prompt. With routing, a message like "check the firewall rules" only includes tools from the `network` and `security` domains -- typically 5-10 tools instead of 50.

## How It Works

```
User message: "What's the SSL status on production servers?"
                    |
                    v
          +-------------------+
          |   Context Router  |
          |   (GPT-4o-mini)   |
          +-------------------+
          | Input:            |
          |  - message text   |
          |  - domain list    |
          | Output:           |
          |  - 1-3 domains    |
          +-------------------+
                    |
                    v
          Matched domains: ["ssl", "servers"]
                    |
                    v
          Filter tools to matched domains
                    |
                    v
          Build prompt with filtered tools
                    |
                    v
          Main LLM (Claude) generates response
```

### Step-by-Step Flow

1. **Extract domains**: The platform collects all unique domains from your registered tools
2. **Classify**: GPT-4o-mini receives the user message and the domain list, returning 1-3 matching domains
3. **Filter**: Only tools whose `domains` field contains at least one matched domain are included in the prompt
4. **Execute**: The main LLM (Claude) sees only relevant tools and generates a response

### Why GPT-4o-mini?

The router uses GPT-4o-mini for classification because:
- It completes in **< 500ms** (typically 200-300ms)
- It costs **< $0.0001** per classification
- Domain classification is a simple task that does not require a large model
- It runs in parallel with history loading, adding minimal latency

## Domain Matching

Each tool declares one or more domains when registered. The router maps user intent to these domains.

### Tool Registration with Domains

```python
@tool(
    name="check_ssl_certificate",
    description="Check SSL certificate status and expiry for a domain",
    domains=["ssl", "security"]
)
async def check_ssl_certificate(ctx: ToolContext, domain: str) -> dict:
    ...

@tool(
    name="list_servers",
    description="List all managed servers with their status",
    domains=["servers", "infrastructure"]
)
async def list_servers(ctx: ToolContext) -> dict:
    ...

@tool(
    name="create_dns_record",
    description="Create a DNS record for a domain",
    domains=["dns"]
)
async def create_dns_record(ctx: ToolContext, domain: str, record_type: str, value: str) -> dict:
    ...
```

### How Matching Works

For the message "What's the SSL status on production servers?":

```
Available domains: ["ssl", "security", "servers", "infrastructure", "dns", "email", "billing"]

Router output: ["ssl", "servers"]

Tool filtering:
  check_ssl_certificate  -> domains: ["ssl", "security"]     -> MATCH (ssl)
  list_servers           -> domains: ["servers", "infra"]     -> MATCH (servers)
  create_dns_record      -> domains: ["dns"]                  -> EXCLUDED
  send_email             -> domains: ["email"]                -> EXCLUDED
  get_invoice            -> domains: ["billing"]              -> EXCLUDED
```

Result: Only `check_ssl_certificate` and `list_servers` appear in the assistant's prompt.

## Optimization: Small Domain Sets

When your extension has **2 or fewer unique domains**, the router skips the LLM call entirely and returns all domains. This is a deliberate optimization:

```python
# If total unique domains <= 2, skip LLM classification
if len(all_domains) <= 2:
    return all_domains  # No LLM call, 0 tokens, 0 latency
```

**Why?** With only 1-2 domains, filtering provides no benefit -- the tool list is already small enough. Skipping the LLM saves 200-300ms of latency and a few tokens of cost.

### When This Applies

| Scenario | Domains | Router Behavior |
|----------|---------|----------------|
| Simple bot with 3 tools, all `["support"]` | 1 | Skip LLM, return all |
| Bot with `["orders", "shipping"]` tools | 2 | Skip LLM, return all |
| Bot with `["orders", "shipping", "inventory"]` | 3 | LLM classifies |
| Complex extension with 10 domains | 10 | LLM classifies |

## Fallback Behavior

The router is designed to be **non-blocking**. If classification fails for any reason, the system falls back gracefully:

### Failure Scenarios

| Failure | Fallback | User Impact |
|---------|----------|-------------|
| LLM API timeout (>3s) | Return all domains | Slightly larger prompt, no functional impact |
| LLM returns invalid JSON | Return all domains | Same as above |
| LLM returns 0 domains | Return all domains | Same as above |
| LLM returns >3 domains | Truncate to first 3 | Minimal -- top 3 are most relevant |

### Timeout

The router enforces a strict **3-second timeout**. If GPT-4o-mini does not respond within 3 seconds, the router returns all domains and processing continues. In practice, timeouts occur in < 0.1% of requests.

```
Timeline (normal):
  0ms    -> Send to GPT-4o-mini
  250ms  -> Receive domains ["ssl", "servers"]
  250ms  -> Continue to main LLM

Timeline (timeout):
  0ms    -> Send to GPT-4o-mini
  3000ms -> Timeout! Return all domains
  3000ms -> Continue to main LLM (all tools included)
```

### First Tool Used Fallback

When fallback returns all domains and the assistant calls a tool, the system uses the **first tool called** as an implicit domain signal for subsequent routing in the same session. This self-correcting behavior means that even after a fallback, the second message in the conversation is likely to be routed correctly.

## Designing Good Domains

Domain design is critical to routing accuracy. Well-designed domains lead to precise tool selection; poorly designed domains cause tools to be included unnecessarily or excluded incorrectly.

### Naming Conventions

**Do:**
- Use specific, descriptive names: `ssl`, `dns`, `billing`, `user-management`
- Use lowercase with hyphens for multi-word domains: `threat-intelligence`
- Keep domain names to 1-2 words

**Do not:**
- Use vague names: `general`, `misc`, `other`, `utils`
- Use overly broad names: `admin` (too many tools would match)
- Use single-character or abbreviated names: `sec`, `net`, `db`

### Controlling Overlap

Some overlap between domains is natural and desirable. A tool that checks SSL certificates reasonably belongs in both `ssl` and `security`. However, excessive overlap defeats the purpose of routing.

**Good overlap (intentional):**
```python
@tool(name="check_ssl", domains=["ssl", "security"])       # SSL is a security concern
@tool(name="block_ip", domains=["security", "firewall"])    # Firewall is security
```

**Bad overlap (too broad):**
```python
@tool(name="check_ssl", domains=["ssl", "security", "servers", "web", "infrastructure"])
# This tool matches almost every domain -- routing cannot help
```

**Rule of thumb:** A tool should have 1-2 domains. If you need 3, reconsider whether one of them is too vague.

### Granularity Guidelines

| Extension Size | Recommended Domains | Example |
|---------------|-------------------|---------|
| 1-5 tools | 1-2 domains | `["support"]` |
| 6-15 tools | 3-5 domains | `["orders", "shipping", "inventory", "returns"]` |
| 16-30 tools | 5-8 domains | `["servers", "ssl", "dns", "email", "firewall", "monitoring"]` |
| 30+ tools | 8-12 domains | Fine-grained by functional area |

More than 12 domains is rarely necessary. If you find yourself creating very many domains, consider whether some tools could be merged or whether your extension should be split into multiple apps.

## Examples

### Example 1: E-Commerce Extension

```python
# Domains: orders, products, customers, shipping

@tool(name="get_order", domains=["orders"])
@tool(name="cancel_order", domains=["orders"])
@tool(name="search_products", domains=["products"])
@tool(name="update_stock", domains=["products"])
@tool(name="get_customer", domains=["customers", "orders"])
@tool(name="track_shipment", domains=["shipping", "orders"])
```

User messages and routing:

| Message | Routed Domains | Tools Available |
|---------|---------------|-----------------|
| "Where is order #1234?" | `orders`, `shipping` | get_order, cancel_order, get_customer, track_shipment |
| "Do we have blue widgets in stock?" | `products` | search_products, update_stock |
| "Show me customer info for john@example.com" | `customers` | get_customer |

### Example 2: DevOps Extension

```python
# Domains: servers, deployments, monitoring, incidents

@tool(name="list_servers", domains=["servers"])
@tool(name="restart_server", domains=["servers"])
@tool(name="deploy_app", domains=["deployments"])
@tool(name="rollback_deploy", domains=["deployments"])
@tool(name="get_metrics", domains=["monitoring"])
@tool(name="check_alerts", domains=["monitoring", "incidents"])
@tool(name="create_incident", domains=["incidents"])
@tool(name="resolve_incident", domains=["incidents"])
```

User messages and routing:

| Message | Routed Domains | Tools Available |
|---------|---------------|-----------------|
| "Deploy v2.3 to production" | `deployments` | deploy_app, rollback_deploy |
| "Server response times are high" | `monitoring`, `servers` | list_servers, restart_server, get_metrics, check_alerts |
| "Create an incident for the outage" | `incidents` | check_alerts, create_incident, resolve_incident |

### Example 3: Minimal Extension (Router Skip)

```python
# Only 2 domains: router skips LLM entirely

@tool(name="ask_question", domains=["knowledge"])
@tool(name="search_docs", domains=["knowledge"])
@tool(name="summarize_doc", domains=["knowledge"])
@tool(name="create_ticket", domains=["support"])
@tool(name="get_ticket", domains=["support"])
```

With only 2 unique domains (`knowledge`, `support`), every message includes all 5 tools. The router adds zero latency.

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Classification latency (p50) | 200ms |
| Classification latency (p95) | 450ms |
| Classification latency (p99) | 800ms |
| Timeout threshold | 3,000ms |
| Timeout rate | < 0.1% |
| Accuracy (correct domain in top-3) | > 95% |
| Cost per classification | < $0.0001 |
| Token usage per classification | ~100-200 tokens |

## Debugging Domain Routing

If tools are not being selected when expected, check these common causes:

1. **Domain name mismatch**: The tool's domain does not match what the router would infer from the user's message. Rename the domain to be more intuitive.

2. **Missing domain on tool**: A tool only appears if at least one of its domains matches. Add the missing domain.

3. **Overly specific domains**: If your domain is `ssl-certificate-renewal` but users say "check SSL," the router may not match. Use broader terms: `ssl`.

4. **Too many domains**: If a tool has 4+ domains, it appears in too many prompts. Reduce to 1-2 focused domains.

You can verify routing behavior by checking the trace in SigNoz, which logs the router's input domains and output classification for each message.

## Related Documentation

- [Tools](tools.md) -- Defining tools with the `@tool` decorator and domain assignments
- [Sessions and History](sessions-and-history.md) -- How sessions process messages after routing
- [Developer Guide](developer-guide.md) -- End-to-end workflow including domain design
- [Concepts](concepts.md) -- ICNLI architecture and how the router fits in
