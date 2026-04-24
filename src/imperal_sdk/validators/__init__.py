# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
"""Structural validator rules (V14+).

Validators in this package operate on an extension *source tree* (Path) via
AST + filesystem inspection, independent from any loaded Extension instance.
Used by the deploy-time pipeline (Developer Portal + `imperal validate`
CLI) to reject v1-era code that imports or declares removed APIs.

Registered rules:
  - V14 ``run_v14`` — reject ChatExtension + ``_system_prompt`` +
    ``llm_orchestrator=True`` + ``prompts/system_prompt.txt`` +
    ``prompts/intake.txt`` (SDK v2.0.0).
"""
from imperal_sdk.validators.v14_no_chatext import V14Result, run_v14

__all__ = ["V14Result", "run_v14"]
