# tests/test_sdl_facet_exports.py
"""SDL Phase 2 — facets re-exported from imperal_sdk.sdl."""
from __future__ import annotations

import imperal_sdk.sdl as sdl

_EXPECTED = [
    "Localized", "Versioned", "Iconified", "Lifecycle",
    "Timestamped", "Schedulable", "Duration", "Recurring", "Booked",
    "Authorship", "Assignable", "Participants", "Correspondents", "ContactPoints", "Presence",
    "Bodied", "Excerptable", "Categorized", "Attached", "Editorial",
    "Conversational", "Threaded", "MessageState", "Reactable", "Callable", "Draftable",
    "FileObject", "ImageMedia", "AudioTrack", "VideoTrack", "Archive", "ContentSafety", "Transcribable",
    "Measured", "Range", "Dimensions3D", "Area", "Angle", "Bitrate", "DataSize", "Temperature", "Length", "Weight", "Speed", "Percentage",
    "Monetary", "Priced", "Discountable", "Subscribable", "Balanced", "Invoiced",
    "Branded", "Inventory", "Bundle", "ColorMaterial", "ProductCompliance",
    "Prioritized", "Progress", "Completable", "Blockable", "Dependencies", "Boarded", "Checklist", "WorkflowState", "Approvable", "Estimable",
    "Geolocated", "PostalAddress", "AdminRegion", "BoundingBox", "Geofence", "Routed", "Placed",
    "NetAsset", "ApiEndpoint", "HostResource", "ComputeSpec", "Container", "ServiceHealth", "Certificated", "DataRecord", "ConfigSetting", "Backup",
    "Aggregated", "TimeSeriesPoint", "Trended", "Confident", "Threshold", "Dimensioned",
    "Eventful", "Capacity", "RSVP", "Ticketed", "AdmissionPolicy", "AgendaSlot", "Cancellation", "CalendarFeed",
    "Rated", "Reviewed", "Sentiment", "Voted",
    "AccessLeveled", "Permissioned", "Auditable", "Consented", "Compliant", "Attested", "Signed", "Retained", "Alertable", "Caseable", "RiskScored",
    "DeviceIdentity", "DeviceState", "SensorReading", "ActuatorState", "Consumable", "ActivityMetrics", "BodyComposition", "VitalSign", "Biometric", "SleepRecord", "AIProvenance",
]


def test_all_facets_exported_from_sdl():
    missing = [n for n in _EXPECTED if not hasattr(sdl, n)]
    assert not missing, f"missing facet exports: {missing}"
