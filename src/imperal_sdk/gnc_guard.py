"""
GNC Lyapunov Guard for Autonomous Long-Running Marathons (RFC: ICNLI V17)

Replaces scalar 1D Lyapunov error V(q, p) with a composite multi-scale potential:
  V(S) = alpha * (1 - MacroCoverage)^2 + beta * ||x_micro||^2 + gamma * Psi(tau_dwell)

Features:
  1. Sub-manifold Limit Cycle Detection (prevents 70,000s traps like Ignat's marathon)
  2. Macro-Velocity Governor (tracks coverage progress per step/time)
  3. Anti-Yak-Shaving Barrier (caps recursion depth <= 2 and forces scratchpad deferral)
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class GNCEnergyState:
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


class GNCLyapunovGuard:
    """
    Composite Multi-Scale Lyapunov Stability Guard.
    Directly connected to Tenant Vault Working RAM.
    """

    def __init__(
        self,
        alpha: float = 10.0,       # Macro-weight (high penalty for unfinished system)
        beta: float = 1.0,         # Micro-weight (local syntax/test error)
        gamma: float = 5.0,        # Barrier weight for dwelling/stalling
        max_dwell_steps: int = 12, # Max allowed steps on one entity before alarm
        max_subtask_depth: int = 2 # Anti-Yak-Shaving depth barrier
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.max_dwell_steps = max_dwell_steps
        self.max_subtask_depth = max_subtask_depth
        
        self.history: List[GNCEnergyState] = []
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
    ) -> GNCEnergyState:
        """
        Calculates composite Lyapunov energy V(S) and checks stability criteria.
        """
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

        # Detect limit cycle / stall
        is_limit_cycle = False
        alarm_reason = None

        # Check Depth Barrier (Anti-Yak-Shaving)
        if subtask_depth > self.max_subtask_depth:
            is_limit_cycle = True
            alarm_reason = (
                f"Anti-Yak-Shaving Barrier tripped: subtask depth {subtask_depth} exceeds "
                f"limit {self.max_subtask_depth}. Refuse deep refactoring; defer blocker to scratchpad."
            )
        # Check Dwell Barrier
        elif dwell > self.max_dwell_steps:
            is_limit_cycle = True
            alarm_reason = (
                f"Limit cycle detected on '{active_entity_id}': dwell steps ({dwell}) exceeded "
                f"budget ({self.max_dwell_steps}) with zero macro coverage gain. Forcing phase transition!"
            )
        # Check Energy Divergence
        elif delta_v > 0.5 and dwell > 5:
            is_limit_cycle = True
            alarm_reason = (
                f"Lyapunov energy diverging (Delta V = +{delta_v:.3f}): system is expanding energy "
                f"on secondary details without macroscopic convergence."
            )

        state = GNCEnergyState(
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
