# tests/contract/test_reference_no_leak.py
"""
Seal gate (L0 success #4): the open Apache-2.0 SDK catalog must not expose
engine-internal tokens in any publicly-visible field (name, description,
parameters, etc.).

Forbidden token rationale:
  temporal / temporalio / workflow_id / run_id / task_queue /
  DirectCallWorkflow — Temporal orchestration engine internals
  redis              — message-broker/pub-sub implementation detail

Note on "namespace":
  "namespace" is a common English word (Python namespaces, DNS namespaces,
  etc.) and produces false positives in generic SDK prose.  The *engine*
  concept is always paired with "temporal" (e.g. "temporal namespace") —
  catching "temporal" is sufficient.  "namespace" is intentionally excluded
  from the forbidden set to avoid false positives.
"""

import json

from imperal_sdk.devtools.generate_reference import generate_reference

FORBIDDEN = (
    "temporal",
    "temporalio",
    "workflow_id",
    "run_id",
    "task_queue",
    "directcallworkflow",
    "redis",
)


def test_catalog_has_no_engine_tokens():
    blob = json.dumps(generate_reference()).lower()
    hits = [tok for tok in FORBIDDEN if tok in blob]
    assert hits == [], (
        f"engine tokens leaked into open SDK catalog: {hits}\n"
        "Scrub the offending public docstring(s) to substrate-neutral wording "
        "(e.g. 'platform execution', 'platform event store')."
    )
