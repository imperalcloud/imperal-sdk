# SDL Facet Library — Developer Guide

The **Structured Data Layer (SDL)** lets your `@chat.function` return typed entities that the platform can read, render, and act on — without any name-guessing. You compose `sdl.Entity` with one or more **facets**: thin mixins that add optional, semantically-tagged fields to your entity class. Every facet field carries a standard role (e.g. `time.created_at`, `task.priority`) so the platform knows exactly what each field means regardless of your extension's naming conventions.

## Quick start

```python
from imperal_sdk import sdl
from imperal_sdk.chat import ChatExtension, ActionResult

chat = ChatExtension(...)

class Task(sdl.Entity, sdl.Schedulable, sdl.Prioritized, sdl.Progress):
    estimate_s: int | None = None

@chat.function("get_task", "Open a task", action_type="read", data_model=Task)
async def get_task(ctx, params) -> ActionResult:
    return ActionResult.success(
        Task(id=7, title="Ship SDL", priority="high", progress=0.5),
        summary="Task loaded.",
    )
```

## Rules

- **All facet fields are optional** — every field defaults to `None` (or `[]` for list fields). Facets add capability; they never introduce required fields beyond the `Entity` core (`id`, `title`, `kind`, plus optional `subtitle`, `description`, `status`, `url`).
- **The platform reads roles directly** — you do not need to match a specific field name. Mix in `Schedulable` and the platform knows `start_at` means `time.start_at`, regardless of your entity's class name.
- **Custom fields** — for anything not covered by a standard facet, use `sdl.field(role="yourapp.something")` where `yourapp` is a namespace you own (any non-reserved namespace). Do not use reserved namespaces (`core`, `time`, `people`, `content`, `comm`, `media`, `quantity`, `money`, `catalog`, `task`, `geo`, `net`, `metric`, `event`, `rating`, `sec`, `device`) for custom fields.
- **Collision-safe composition** — all 123 standard facets are designed to be mixed into the same entity without field-name conflicts.

---

## Family reference

### Identity & Provenance (`core.*`)

Use these facets to describe localization, versioning, iconography, and lifecycle state of an entity.

**Localized** — multi-language metadata:
`language`, `languages`, `text_direction`, `locale`, `localized_title`, `localized_description`, `available_locales`

**Versioned** — release and revision tracking:
`version`, `semver`, `revision`, `revision_of`, `is_latest`, `content_hash`, `channel`, `released_at`

**Iconified** — visual identity:
`icon`, `emoji`, `color_hex`, `avatar_url`

**Lifecycle** — soft-delete, pin, favourite, and visibility state:
`is_archived`, `is_pinned`, `is_favorite`, `is_deleted`, `visibility`

---

### Time (`time.*`)

Use these facets to describe timestamps, schedules, durations, recurrence patterns, and booking windows.

**Timestamped** — creation and modification times:
`created_at`, `updated_at`, `deleted_at`

**Schedulable** — start/end/due windows and timezone:
`start_at`, `end_at`, `due_at`, `all_day`, `timezone`

**Duration** — how long something takes:
`duration_s`, `duration_display_unit`

**Recurring** — repeating occurrences:
`recurrence_rule`, `recurrence_until`, `recurrence_count`, `is_recurring_master`, `next_occurrence_at`, `recurrence_anchor`

**Booked** — reservation lifecycle:
`booked_at`, `check_in_at`, `check_out_at`, `cancelled_at`, `cancellation_deadline`

---

### People & Identity (`people.*`)

Use these facets to associate people, teams, and contact information with an entity.

**Authorship** — who created or owns it:
`creator`, `author`, `owner`, `last_editor`, `editors`, `contributors`

**Assignable** — who is responsible for it:
`assignee`, `assignees`, `reviewer`, `reviewers`, `team`, `delegated_by`, `assigned_at`

**Participants** — group membership and presence:
`members`, `admins`, `host`, `organizer`, `participant_count`, `active_now`, `typing`, `join_state`

**Correspondents** — email/message addressing:
`sender`, `recipients_to`, `recipients_cc`, `recipients_bcc`, `reply_to`, `recipient_count`

**ContactPoints** — contact channels:
`emails`, `phones`, `social_handles`, `website_url`, `preferred_channel`

**Presence** — real-time availability:
`online_status`, `status_message`, `status_emoji`, `last_seen_at`, `active_until`

---

### Content & Documents (`content.*`)

Use these facets for entities that carry body text, summaries, categories, attachments, or editorial workflow state.

**Bodied** — rich body content:
`body`, `body_format`, `raw_body`

**Excerptable** — preview and readability metadata:
`excerpt`, `summary`, `word_count`, `reading_time_s`

**Categorized** — tags, categories, topics, and labels:
`tags`, `categories`, `topics`, `keywords`, `labels`

**Attached** — file and image attachments:
`attachments`, `attachment_count`, `has_attachments`, `inline_images`

**Editorial** — publishing workflow:
`editorial_state`, `is_draft`, `published_at`, `first_published_at`

---

### Communication (`comm.*`)

Use these facets for messaging, conversation threads, delivery state, reactions, calls, and drafts.

**Conversational** — conversation-level metadata:
`conversation_ref`, `conversation_type`, `channel_name`, `is_group`, `conversation_participant_count`, `last_message_at`, `last_preview`

**Threaded** — reply chains and nesting:
`thread_ref`, `reply_to_message`, `root`, `depth`

**MessageState** — delivery and read state:
`direction`, `is_read`, `delivery_state`, `sent_at`, `edited_at`, `is_from_me`

**Reactable** — emoji reactions:
`reactions`, `reaction_count`, `my_reactions`

**Callable** — voice/video call metadata:
`call_direction`, `call_type`, `call_state`, `answered`, `end_reason`, `ring_duration_s`

**Draftable** — draft and scheduled-send state:
`is_draft`, `scheduled_send_at`, `last_saved_at`, `is_auto_generated`

---

### Media & Files (`media.*`)

Use these facets for files, images, audio/video tracks, archives, content safety scanning, and transcription.

**FileObject** — generic file descriptor:
`filename`, `extension`, `mime_type`, `size_bytes`, `media_class`, `path`, `checksum_sha256`, `permissions`

**ImageMedia** — image dimensions and metadata:
`width`, `height`, `color_space`, `exif`, `blurhash`

**AudioTrack** — audio encoding properties:
`audio_codec`, `bitrate_kbps`, `sample_rate_hz`, `channels`, `bit_depth`, `loudness_lufs`

**VideoTrack** — video encoding properties:
`video_codec`, `resolution`, `fps`, `video_bitrate_kbps`, `hdr`

**Archive** — compressed archive metadata:
`archive_format`, `entry_count`, `uncompressed_size_bytes`, `compression_ratio`, `is_encrypted`

**ContentSafety** — moderation and virus scan results:
`scan_state`, `is_nsfw`, `moderation_labels`, `virus_name`, `scanned_at`

**Transcribable** — speech-to-text output:
`transcript`, `captions_url`, `transcript_language`

---

### Quantities & Units (`quantity.*`)

Use these facets for measured values with units, ranges, physical dimensions, and common physical quantities.

**Measured** — a generic scalar measurement:
`value`, `unit`, `dimension`, `unit_family`, `value_type`, `uncertainty`, `formatted_value`

**Range** — a bounded numeric range with optional target:
`min_value`, `max_value`, `target`

**Dimensions3D** — physical width/height/depth:
`dim_width`, `dim_height`, `dim_depth`, `dim_unit`

**Area** — surface area:
`area_m2`, `area_unit`

**Angle** — angular measurement:
`angle_deg`, `angle_unit`

**Bitrate** — data transfer rate:
`bitrate_bps`, `bitrate_unit`

**DataSize** — storage size in bytes:
`bytes`, `data_size_unit`

**Temperature** — temperature reading:
`temp_c`, `temp_unit`

**Length** — linear measurement:
`length_m`, `length_unit`

**Weight** — mass measurement:
`weight_kg`, `weight_unit`

**Speed** — velocity measurement:
`speed_mps`, `speed_unit`

**Percentage** — a fractional percentage value:
`percent`

---

### Money & Commerce (`money.*`)

Use these facets for monetary values, pricing, discounts, subscriptions, account balances, and invoices.

**Monetary** — a simple currency amount:
`amount`, `currency`

**Priced** — product pricing with list/compare prices:
`unit_price`, `list_price`, `compare_at_price`, `price_currency`, `price_includes_tax`

**Discountable** — sale pricing and discount percentage:
`sale_price`, `discount_pct`, `is_on_sale`

**Subscribable** — subscription billing state and intervals:
`subscription_status`, `billing_interval`, `billing_interval_count`, `current_period_start`, `current_period_end`, `trial_end`, `recurring_amount`, `cancel_at_period_end`

**Balanced** — account balance breakdown:
`balance`, `balance_currency`, `available_balance`, `pending_balance`, `credit_limit`

**Invoiced** — invoice and payment state:
`invoice_number`, `total`, `tax`, `payment_status`, `paid_at`, `invoice_due_at`

---

### Catalog, Products & Inventory (`catalog.*`)

Use these facets for product catalog entities: brand identity, stock levels, bundles, materials, and compliance.

**Branded** — brand and manufacturer identity:
`brand`, `manufacturer`, `model_name`, `model_year`, `country_of_origin`

**Inventory** — stock availability:
`in_stock`, `availability`, `low_stock_threshold`, `is_low_stock`, `backorderable`, `preorder`

**Bundle** — product bundle composition:
`is_bundle`, `bundle_items`, `bundle_type`

**ColorMaterial** — visual and material attributes:
`color`, `color_hex`, `material`, `pattern`, `finish`

**ProductCompliance** — regulatory and age-restriction metadata:
`certifications`, `hs_code`, `age_restriction`, `restricted_regions`, `requires_prescription`

---

### Tasks & Workflow (`task.*`)

Use these facets for task management: priority, progress, completion, blockers, dependencies, kanban boards, checklists, workflow states, approvals, and time estimates.

**Prioritized** — priority, urgency, and severity levels:
`priority`, `urgency`, `severity`

**Progress** — completion percentage and item counts:
`progress`, `done_count`, `total_count`

**Completable** — done state and resolution:
`is_done`, `completed_at`, `completed_by`, `resolution`

**Blockable** — blocker state and reason:
`is_blocked`, `blocked_reason`, `blocked_since`, `waiting_on`

**Dependencies** — upstream and downstream task links:
`blocks`, `blocked_by`, `related`

**Boarded** — kanban board and column placement:
`board`, `column`, `swimlane`, `position`

**Checklist** — subtask checklists:
`checklist_items`, `checked_count`, `checklist_total`

**WorkflowState** — state machine position and transitions:
`state`, `allowed_transitions`, `entered_state_at`

**Approvable** — approval workflow:
`approval_status`, `approver`, `decided_at`, `decision_note`

**Estimable** — time estimates and actuals:
`estimate_s`, `spent_s`, `remaining_s`

---

### Location & Geo (`geo.*`)

Use these facets for geographic coordinates, postal addresses, administrative regions, bounding boxes, geofences, routing, and named places.

**Geolocated** — GPS/GNSS coordinates with accuracy:
`lat`, `lon`, `altitude_m`, `accuracy_m`, `heading_deg`, `geo_speed_mps`, `located_at`

**PostalAddress** — mailing address:
`street`, `city`, `postal_code`, `region`, `country`

**AdminRegion** — administrative hierarchy:
`country_code`, `region_code`, `county`, `locality`, `neighborhood`, `continent`

**BoundingBox** — geographic bounding rectangle:
`min_lat`, `min_lon`, `max_lat`, `max_lon`

**Geofence** — circular geofence with trigger conditions:
`center_lat`, `center_lon`, `radius_m`, `trigger`, `dwell_s`

**Routed** — origin/destination routing:
`origin`, `destination`, `distance_m`, `route_duration_s`, `waypoints`

**Placed** — named place identity:
`place_name`, `place_type`, `plus_code`

---

### Tech / Infra / Network / Data (`net.*`)

Use these facets for infrastructure entities: network assets, API endpoints, hosts, compute specs, containers, service health, TLS certificates, data records, config settings, and backups.

**NetAsset** — a DNS/IP network resource:
`domain`, `ip`, `port`, `protocol`, `record_type`

**ApiEndpoint** — an HTTP API operation:
`method`, `api_path`, `operation_id`, `auth_required`, `deprecated`

**HostResource** — a named host or cloud resource:
`hostname`, `resource_id`, `environment`, `host_region`

**ComputeSpec** — CPU/memory/disk/GPU capacity:
`vcpus`, `memory_bytes`, `disk_bytes`, `gpu_count`, `arch`

**Container** — a running container or service:
`container_id`, `container_name`, `image`, `image_digest`, `runtime`, `compose_project`

**ServiceHealth** — health check and uptime:
`health`, `uptime_s`, `last_check_at`

**Certificated** — TLS/X.509 certificate metadata:
`cert_issuer`, `cert_subject`, `not_after`, `fingerprint`, `cert_is_valid`

**DataRecord** — a database row or query result:
`table`, `row_id`, `query`, `schema_ref`

**ConfigSetting** — a configuration key/value pair:
`config_key`, `config_value`, `config_value_type`, `is_secret`, `config_source`, `default_value`

**Backup** — a point-in-time backup snapshot:
`snapshot_id`, `source_resource`, `taken_at`, `backup_size_bytes`, `retain_until`, `backup_kind`, `is_verified`

---

### Analytics & Metrics (`metric.*`)

Use these facets for aggregated metrics, time series points, trends, statistical confidence, thresholds, and multi-dimensional data.

**Aggregated** — a windowed aggregation:
`aggregation`, `window_start`, `window_end`, `granularity`, `fill_policy`

**TimeSeriesPoint** — a single time series data point:
`ts_timestamp`, `ts_value`

**Trended** — delta and trend direction:
`delta`, `change_pct`, `trend`, `trend_period`

**Confident** — statistical confidence interval:
`confidence_level`, `ci_lower`, `ci_upper`, `margin_of_error`, `p_value`, `is_significant`

**Threshold** — alert threshold and breach state:
`threshold_target`, `threshold`, `breached`

**Dimensioned** — arbitrary dimension labels for a metric:
`dimensions`

---

### Events & Tickets (`event.*`)

Use these facets for calendar events, venue capacity, RSVPs, tickets, admission policies, agenda slots, cancellations, and calendar feed integration.

**Eventful** — event venue and organizer:
`venue`, `event_organizer`, `event_host`, `event_type`

**Capacity** — attendee capacity and availability:
`capacity_total`, `capacity_remaining`, `registered_count`, `waitlist_count`, `is_sold_out`

**RSVP** — a person's RSVP and check-in state:
`rsvp_state`, `checked_in`, `is_no_show`, `check_in_method`

**Ticketed** — ticket and seat assignment:
`ticket_type`, `seat`, `barcode`, `ticket_price`

**AdmissionPolicy** — entry requirements:
`min_age`, `dress_code`, `requires_id`, `prohibited_items`, `doors_open_at`

**AgendaSlot** — a session within an event program:
`parent_event`, `track`, `session_type`, `order_index`, `speakers`

**Cancellation** — event or booking cancellation and refund policy:
`is_cancelled`, `refund_policy`, `refund_deadline`, `is_refundable`

**CalendarFeed** — iCal/ICS feed integration:
`ical_uid`, `ics_url`, `feed_url`, `calendar_name`, `calendar_color`

---

### Ratings & Feedback (`rating.*`)

Use these facets for star ratings, written reviews, sentiment analysis, and voting.

**Rated** — aggregate star/score rating:
`rating`, `max_score`, `rating_count`, `distribution`

**Reviewed** — a written review with verification:
`review_body`, `is_verified`, `helpfulness`, `would_recommend`

**Sentiment** — NLP sentiment classification:
`sentiment`, `sentiment_score`, `magnitude`

**Voted** — upvote/downvote counts:
`upvotes`, `downvotes`, `score`, `my_vote`

---

### Security / Legal / Compliance / Audit (`sec.*`)

Use these facets for access classification, permissions, audit logs, consent records, compliance controls, attestations, digital signatures, retention policies, alerts, case management, and risk scoring.

**AccessLeveled** — data classification and access visibility:
`classification`, `clearance_required`, `access_visibility`, `handling_caveats`

**Permissioned** — RBAC and CRUD permission flags:
`sec_permissions`, `role`, `can_read`, `can_write`, `can_delete`, `can_share`

**Auditable** — an audit trail entry:
`actor`, `action`, `audit_target`, `occurred_at`, `outcome`, `source_ip`, `changes`

**Consented** — a data consent record:
`consent_purpose`, `consent_state`, `consent_subject`, `granted_at`, `legal_basis`, `consent_proof`

**Compliant** — a compliance control assessment:
`framework`, `control_id`, `compliance_status`, `last_assessed_at`, `assessed_by`

**Attested** — a verification attestation:
`attestation_type`, `attestation_result`, `attested_by`, `attestation_confidence`

**Signed** — a digital signature:
`signature`, `signer`, `algorithm`, `signature_is_valid`, `signed_at`

**Retained** — data retention and legal hold:
`retention_class`, `sec_retain_until`, `legal_hold`

**Alertable** — a monitoring alert:
`alert_severity`, `alert_state`, `fired_at`, `resolved_at`, `rule_name`, `alert_threshold`

**Caseable** — a legal or support case:
`case_number`, `case_type`, `case_stage`, `opened_at`, `closed_at`, `case_resolution`, `jurisdiction`

**RiskScored** — a risk score and level:
`risk_score`, `risk_level`, `risk_factors`

---

### Devices / IoT / Sensors / Health (`device.*`)

Use these facets for IoT devices, sensors, actuators, consumables, fitness activity, body composition, vital signs, biometrics, sleep records, and AI provenance.

**DeviceIdentity** — device hardware identity:
`device_id`, `device_model`, `device_manufacturer`, `firmware_version`, `serial`

**DeviceState** — battery, signal, and connectivity state:
`online`, `battery_pct`, `signal_strength`, `device_last_seen_at`

**SensorReading** — a sensor measurement:
`sensor_type`, `sensor_value`, `sensor_unit`, `measured_at`, `quality`

**ActuatorState** — the state of a controllable device:
`on`, `level_pct`, `mode`, `locked`, `actuator_position`, `color_temp_k`, `actuator_color_hex`

**Consumable** — a replaceable consumable (ink, filter, battery):
`consumable_type`, `remaining_pct`, `replace_after_at`, `low`

**ActivityMetrics** — fitness activity summary:
`steps`, `activity_distance_m`, `active_calories_kcal`, `active_minutes`, `floors_climbed`

**BodyComposition** — body measurement snapshot:
`body_weight_kg`, `bmi`, `body_fat_pct`, `muscle_mass_kg`, `body_measured_at`

**VitalSign** — clinical vital signs:
`heart_rate_bpm`, `blood_pressure`, `spo2_pct`, `body_temp_c`, `respiratory_rate`

**Biometric** — a biometric measurement:
`biometric_type`, `biometric_value`, `biometric_unit`, `biometric_measured_at`, `biometric_context`, `reference_low`, `reference_high`

**SleepRecord** — a sleep session:
`sleep_duration_s`, `sleep_stages`, `sleep_quality_score`, `in_bed_at`, `awake_at`

**AIProvenance** — AI generation metadata:
`generated_by_ai`, `ai_model`, `ai_confidence`, `prompt_ref`, `reviewed_by_human`
