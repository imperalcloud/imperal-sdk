# CLI Reference

**Last updated:** 2026-04-18
**SDK version:** imperal-sdk 1.5.7
**Binary:** `imperal`
**Install:** `pip install imperal-sdk`

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `imperal init <name>` | Scaffold a new extension project |
| `imperal build [path]` | Generate `imperal.json` manifest from the Extension object |
| `imperal validate [path]` | Run V1–V12 compliance checks against SDK rules |
| `imperal dev` | Run local development server with hot reload |
| `imperal test` | Run extension tests via pytest |
| `imperal deploy` | Generate manifest and deploy to Imperal Cloud |
| `imperal logs` | Tail production logs from Imperal Cloud |
| `imperal --version` | Print SDK version |
| `imperal --help` | Show help for any command |

---

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Print the SDK version and exit. |
| `--help` | Show help text and exit. Available on every command. |

---

## Commands

### `imperal init`

Scaffold a new extension project with a working directory structure, sample tool, test suite, and dependency file.

**Usage:**

```bash
imperal init <name>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Name of the extension. Used as the directory name and the `app_id` in the generated code. |

**Generated structure:**

```
<name>/
  main.py              # Extension entry point with a sample "hello" tool
  requirements.txt     # Dependency file (imperal-sdk>=0.2.0)
  .gitignore           # Ignores venv, __pycache__, .env, manifest.json
  tests/
    __init__.py
    test_hello.py      # Sample tests for the "hello" tool
```

**Example:**

```bash
imperal init my-extension
# Extension 'my-extension' created!
#   cd my-extension
#   pip install imperal-sdk
#   imperal dev

cd my-extension
```

The generated `main.py` registers a single tool called `hello` that returns a greeting message. Use it as a starting point -- add your own tools, signals, and schedules.

---

### `imperal build`

Generate `imperal.json` manifest for the extension at `PATH` (default: current directory).

**Usage:**

```bash
imperal build [PATH]
```

Loads the extension from `main.py`, generates the manifest from registered tools / signals / schedules / lifecycle hooks / capabilities, merges any existing marketplace fields from a pre-existing `imperal.json`, and writes the result to `imperal.json`.

**Output:**

```
Built: my-extension v1.0.0
  Tools: 3, Signals: 1, Schedules: 0
  Manifest: /path/to/extension/imperal.json
```

---

### `imperal validate`

Validate the extension at `PATH` (default: `.`) against SDK v1.0.0 compliance rules (V1–V12). The CLI exits with non-zero status if any ERROR-level issue is found so it can be wired into CI.

**Usage:**

```bash
imperal validate [PATH]
```

**Rules checked (V1–V12):**

| Rule | Description |
|------|-------------|
| V1 | Exactly one `ChatExtension` entry point |
| V2 | All `@chat.function` handlers return `ActionResult` |
| V3 | No direct `anthropic` imports (use `ctx.ai` / LLM Provider) |
| V4 | All `@chat.function` params use Pydantic `BaseModel` |
| V5 | Write/destructive functions declare `event=` or explicitly omit it |
| V6 | Handler signature typing resolves to supported types under PEP 563 |
| V7+ | Additional rules — see `imperal validate` output |

> **v1.5.7 PEP 563 fix (session 27):** V5 and V6 previously raised false positives on `from __future__ import annotations` with a Pydantic `BaseModel` parameter, because `inspect.Parameter.annotation` returns a string (not a class) under PEP 563. Validators now resolve forward references via `typing.get_type_hints(func)` before `isinstance` / `issubclass`. Three shared helpers (`_resolve_hints`, `_looks_like_action_result`, `_is_basemodel_subclass`) ensure every future type check reuses the same resolution. Pin `imperal-sdk>=1.5.7` to pick up the fix.

**Output (success):**

```
── Imperal Extension Validator v1.0 ────────────────────────────────────

Extension: my-extension v1.0.0
Tools: 1, Functions: 3, Events: 2

✅ No issues found!
```

**Output (with issues):**

```
RESULTS: 1 error(s), 2 warning(s), 0 info

  ERROR main.py:42  [V2] Function 'fn_send' returns dict, expected ActionResult.
         Fix: Return ActionResult.success(...) or ActionResult.error(...)
  WARN  main.py:17  [V5] Function 'fn_send' has action_type='write' but no event=
         Fix: Add event="mail.sent" to @chat.function for Automation triggers.

❌ 1 error(s) must be fixed before deployment.
```

Exit codes: `0` if no errors (warnings allowed), `1` if one or more errors.

**Example:**

```bash
# Validate current directory
imperal validate

# Validate a specific path (used by Developer Portal deep validation)
imperal validate /opt/extensions/my-app
```

---

### `imperal dev`

Start a local development server. Loads the extension from `main.py` in the current directory, generates a manifest, and prints registered tools, signals, and schedules.

**Usage:**

```bash
imperal dev
```

**Requirements:**

- Must be run from the extension root directory (where `main.py` is located).
- `main.py` must export an `ext` object of type `Extension`.

**Output:**

```
Extension: my-extension v0.2.0
Tools: hello
Signals: none
Schedules: none
Dev server ready. Ctrl+C to stop.
```

**Error handling:**

If no `main.py` with an `ext` object is found, the command exits with code 1:

```
Error: No main.py found with 'ext' Extension object.
```

**Example:**

```bash
cd my-extension
imperal dev
```

---

### `imperal test`

Run the extension test suite using pytest. Executes all tests in the `tests/` directory with verbose output.

**Usage:**

```bash
imperal test
```

**Requirements:**

- Must be run from the extension root directory.
- pytest must be installed (`pip install pytest pytest-asyncio`).

**Behavior:**

- Runs `python -m pytest tests/ -v` as a subprocess.
- Exits with the same return code as pytest (0 on success, non-zero on failure).

**Example:**

```bash
cd my-extension
imperal test
# tests/test_hello.py::test_hello_tool_registered PASSED
# tests/test_hello.py::test_hello_tool PASSED
```

---

### `imperal deploy`

Deploy your extension to the Imperal Cloud platform.

**Usage:**

```bash
imperal deploy
```

**Requirements:**

- Must be run from the extension root directory.
- `main.py` must export an `ext` object of type `Extension`.
- App must be registered in Panel first.
- Credentials configured (see below).

**What it does:**

1. Generates manifest from the Extension object
2. Validates tools (descriptions required, scope format checked)
3. Pushes tools with `required_scopes` to Registry (triggers embedding generation)
4. Pushes config defaults to unified config store via Registry Settings API

**Credentials:**

Set via environment variables:

```bash
export IMPERAL_REGISTRY_URL=https://api.imperal.io:8098
export IMPERAL_GATEWAY_URL=https://auth.imperal.io
export IMPERAL_API_KEY=imp_key_xxxxx
```

Or create `.imperal/credentials` (project-local or `~/.imperal/credentials`):

```ini
[default]
registry_url = https://api.imperal.io:8098
gateway_url = https://auth.imperal.io
api_key = imp_key_xxxxx
```

Environment variables override file credentials. Add `.imperal/` to `.gitignore`.

**Output:**

```
Validating extension... OK
Generating manifest... OK
Pushing tools to Registry... OK (embeddings queued)
Pushing config defaults... OK
Deploying to /opt/extensions/my-extension/main.py... OK

Extension deployed:
  App ID:    my-extension
  Tools:     registered
  Status:    active
```

**Example:**

```bash
cd my-extension
imperal deploy
```

---

### `imperal logs`

Tail production logs for the extension from Imperal Cloud (streamed via SigNoz).

**Usage:**

```bash
imperal logs
```

Connects to the platform's log stream and filters output for your extension's `app_id`. Press Ctrl+C to stop.

---

## Typical Workflow

```bash
# 1. Create a new extension
imperal init billing-alerts

# 2. Enter the project directory and install dependencies
cd billing-alerts
pip install -r requirements.txt

# 3. Edit main.py -- add tools, signals, schedules

# 4. Start the dev server to verify registration
imperal dev

# 5. Run tests
imperal test

# 6. Deploy to Imperal Cloud
imperal deploy

# 7. Monitor production logs
imperal logs
```

---

## See Also

- [Quickstart](quickstart.md) -- Build your first extension end-to-end.
- [Deployment Guide](deployment.md) -- Production deployment and Registry configuration.
- [Developer Guide](developer-guide.md) -- Extension architecture, Context API, tools, signals, and schedules.

---

Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
