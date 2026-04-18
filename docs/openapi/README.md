# Imperal OpenAPI Contracts

Canonical OpenAPI 3.x specs for the three Imperal platform services an extension interacts with. Auto-generated from each FastAPI service; regenerated on each release.

| Service | Spec | Paths | Purpose |
|---------|------|-------|---------|
| **Auth Gateway** | [`auth-gateway.json`](auth-gateway.json) | 151 | JWT issuance, users, tenants, apps, billing, automations, agencies — the OS identity layer. Base URL: `https://auth.imperal.io` |
| **Registry** | [`registry.json`](registry.json) | 15 | Extension catalog, tool discovery, per-app settings, hub dispatch — where your extension is registered and its manifest is served. |
| **Sharelock Cases** | [`sharelock-cases.json`](sharelock-cases.json) | 63 | Forensic case store, evidence storage, AI analysis results — only relevant if you're building on top of Sharelock v3. |

**Total: 229 endpoints, 139 schemas, ~570 KB.**

## How to use

### Browse interactively

Paste any of the `*.json` files into [Swagger Editor](https://editor.swagger.io/) or open them in VS Code with the [OpenAPI (Swagger) Editor](https://marketplace.visualstudio.com/items?itemName=42Crunch.vscode-openapi) extension.

### Generate a typed client

```bash
# Python
pip install openapi-python-client
openapi-python-client generate --path docs/openapi/registry.json

# TypeScript
npx openapi-typescript docs/openapi/auth-gateway.json -o types/auth-gateway.d.ts

# Any language
# https://openapi-generator.tech/docs/generators
```

### Validate your code against the contract

```python
import json, jsonschema
spec = json.load(open("docs/openapi/registry.json"))
# Validate a response dict against a component schema:
jsonschema.validate(response_dict, spec["components"]["schemas"]["AppSummary"])
```

### Contract-test your extension

Use [schemathesis](https://schemathesis.readthedocs.io/) against a running service to prove your implementation conforms to the spec:

```bash
pip install schemathesis
schemathesis run docs/openapi/registry.json --base-url https://api.imperal.io
```

## What's *not* here

Internal platform services (DirectAdmin proxy, WHMCS bridge, ad-network controllers, diagnostics) ship on shared infrastructure but are not part of the SDK surface and are intentionally excluded. Extensions interact with them only indirectly through the Auth Gateway / Registry abstractions covered above.

## Regeneration

Specs are captured from each service's `/openapi.json` endpoint. A full regeneration procedure and the authoritative archive (including internal specs) lives in the internal ops repo.
