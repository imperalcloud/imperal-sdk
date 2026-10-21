"""Old names of :mod:`imperal_sdk.dwell_guard`, kept so existing extensions keep importing."""
from imperal_sdk.dwell_guard import DwellGuard as GNCLyapunovGuard, DwellGuardStep as GNCEnergyState

__all__ = ["GNCLyapunovGuard", "GNCEnergyState"]
