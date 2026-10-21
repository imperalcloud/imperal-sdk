"""
Dwell guard for long-running marathons: is the agent stuck on one item?

Each step scores a gap from three measured parts:
  gap = alpha * (1 - coverage)^2 + beta * error^2 + gamma * excess_dwell^2

and raises an alarm when the agent
  1. goes deeper than ``max_subtask_depth`` nested subtasks,
  2. stays on one entity for more than ``max_dwell_steps`` steps without coverage gain, or
  3. lets the gap grow while dwelling.

(``imperal_sdk.gnc_guard`` keeps the old names ``GNCLyapunovGuard`` / ``GNCEnergyState``.)
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class DwellGuardStep:
    step: int
    timestamp: float
    active_entity_id: str
    macro_coverage: float      # [0.0 ... 1.0] from Tenant Vault
    micro_error: float         # [0.0 ... 1.0] local file/test error
    dwell_steps: int           # consecutive steps on active_entity_id without maturity gain
    v_macro: float
    v_micro: float
    v_barrier: float
    v_total: float
    delta_v: float
    is_limit_cycle: bool
    alarm_reason: Optional[str] = None


class DwellGuard:
    """Scores each step's gap and raises an alarm when the agent dwells on one entity."""

    def __init__(
        self,
        alpha: float = 10.0,       # weight of the unfinished share of the plan
        beta: float = 1.0,         # weight of the local error (syntax / test)
        gamma: float = 5.0,        # weight of the steps over the dwell budget
        max_dwell_steps: int = 12, # Max allowed steps on one entity before alarm
        max_subtask_depth: int = 2 # max nesting of subtasks
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.max_dwell_steps = max_dwell_steps
        self.max_subtask_depth = max_subtask_depth
        
        self.history: List[DwellGuardStep] = []
        self._current_subtask_depth: int = 1
        self._last_active_entity: Optional[str] = None
        self._entity_dwell_counter: int = 0
        self._last_macro_coverage: float = 0.0

    def step(
        self,
        macro_coverage: float,
        active_entity_id: str,
        micro_error: float = 0.0,
        subtask_depth: int = 1
    ) -> DwellGuardStep:
        """Scores this step's gap and checks the depth, dwell and growth limits."""
        now = time.time()
        step_num = len(self.history) + 1

        # Track dwell count on active entity
        if active_entity_id == self._last_active_entity:
            # If macro coverage did not increase significantly
            if macro_coverage <= self._last_macro_coverage + 1e-4:
                self._entity_dwell_counter += 1
            else:
                self._entity_dwell_counter = 1
        else:
            self._last_active_entity = active_entity_id
            self._entity_dwell_counter = 1

        self._last_macro_coverage = macro_coverage
        dwell = self._entity_dwell_counter

        # 1. Macro component: quadratic penalty for distance to 100% completion
        macro_gap = max(0.0, 1.0 - macro_coverage)
        v_macro = self.alpha * (macro_gap ** 2)

        # 2. Micro component: local error in active component
        v_micro = self.beta * (micro_error ** 2)

        # 3. Barrier component: quadratic penalty for dwelling beyond budget
        if dwell > self.max_dwell_steps:
            excess = float(dwell - self.max_dwell_steps)
            v_barrier = self.gamma * (excess ** 2)
        else:
            v_barrier = 0.0

        v_total = v_macro + v_micro + v_barrier

        # Compute delta V
        if self.history:
            delta_v = v_total - self.history[-1].v_total
        else:
            delta_v = 0.0

        # Detect a stall
        is_limit_cycle = False
        alarm_reason = None

        # Too many nested subtasks
        if subtask_depth > self.max_subtask_depth:
            is_limit_cycle = True
            alarm_reason = (
                f"Subtask depth {subtask_depth} exceeds the limit {self.max_subtask_depth}: "
                f"do not go deeper; note the blocker and return to the item."
            )
        # Too many steps on one entity
        elif dwell > self.max_dwell_steps:
            is_limit_cycle = True
            alarm_reason = (
                f"Stuck on '{active_entity_id}': {dwell} steps without coverage gain "
                f"(limit {self.max_dwell_steps}). Move to another item or report the blocker."
            )
        # The gap grows while dwelling
        elif delta_v > 0.5 and dwell > 5:
            is_limit_cycle = True
            alarm_reason = (
                f"The gap grew by {delta_v:.3f} while dwelling: the steps go into side details "
                f"without moving the plan."
            )

        state = DwellGuardStep(
            step=step_num,
            timestamp=now,
            active_entity_id=active_entity_id,
            macro_coverage=macro_coverage,
            micro_error=micro_error,
            dwell_steps=dwell,
            v_macro=v_macro,
            v_micro=v_micro,
            v_barrier=v_barrier,
            v_total=v_total,
            delta_v=delta_v,
            is_limit_cycle=is_limit_cycle,
            alarm_reason=alarm_reason
        )
        self.history.append(state)
        return state
