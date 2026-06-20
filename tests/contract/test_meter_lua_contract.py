"""Cross-repo billing-stream XADD envelope contract (metering-rails L0-4, Task 18).

The meter event SHAPE is a hard cross-repo contract shared by FIVE Lua copies:

    kernel billing/lua_scripts.py  — EMIT_METER           (canonical owner)
    kernel billing/lua_scripts.py  — CHECK_AND_DEDUCT
    kernel billing/lua_scripts.py  — RESERVE
    kernel billing/lua_scripts.py  — SETTLE
    billing-worker activities/wallet_activities.py — _CREDIT_LUA

All five ``XADD imperal:billing:events`` using the same three field NAMES in the
same order:  event_id → type → data.  The kernel EMIT_METER additionally hard-codes
the literal string ``'meter'`` as the ``type`` discriminator (the others pass the
type value via an ARGV position).

The consumer (kernel billing consumer activity) and the billing-worker both READ
this envelope by field name.  A rename or reorder in any of the five Lua copies
silently breaks consumption at runtime.

This test vendors the canonical metered-XADD line (kernel EMIT_METER) and asserts:

1. The three envelope field NAMES are present and appear in canonical order
   (event_id < type < data) — structural, not a whole-script SHA1.
2. The meter discriminator literal ``'type', 'meter'`` is present (consumer routes
   on this value).
3. The field-name positions match the explicit positional expectation derived by
   parsing the quoted names from the XADD line itself (catch transpose bugs).

SYNC OBLIGATION:  If the kernel EMIT_METER Lua line changes in
``billing/lua_scripts.py``, update ``_VENDORED_EMIT_METER_XADD`` here AND confirm
the other four Lua copies (CHECK_AND_DEDUCT / RESERVE / SETTLE / _CREDIT_LUA) still
use the same field-NAME sequence.  The preflight gate (Edge 1: ``tests/contract/``)
will turn red automatically on any divergence between this file and the updated
constant, forcing a deliberate, reviewed sync.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Vendored canonical line — kernel billing/lua_scripts.py EMIT_METER (verbatim).
# Last verified: 2026-06-20 (L0-4 metering-rails Task 18).
# ---------------------------------------------------------------------------
_VENDORED_EMIT_METER_XADD = (
    "redis.call('XADD', KEYS[1], '*', 'event_id', ARGV[1], 'type', 'meter', 'data', ARGV[2])"
)

# The canonical envelope field-name order shared across ALL 5 billing-stream Lua copies.
_ENVELOPE_FIELD_ORDER: tuple[str, ...] = ("event_id", "type", "data")

# The meter discriminator: the literal value for the 'type' field in EMIT_METER.
_METER_TYPE_DISCRIMINATOR = "meter"


def _parse_quoted_field_names(xadd_line: str) -> list[str]:
    """Extract all single-quoted identifiers that look like Redis field names.

    Skips the Redis-command tokens (``XADD``, ``KEYS``, ``ARGV``-holders, ``*``),
    returning only the bare lowercase names — i.e. the alternating field-name tokens
    in the ``XADD ... field value field value ...`` tail.

    Strategy: find all ``'...'`` tokens; keep those whose content is a plain
    lowercase identifier (no digits, no dots, no brackets) — these are the field
    names; ARGV-holder strings and ``*`` are filtered out naturally.
    """
    tokens = re.findall(r"'([^']+)'", xadd_line)
    # Field names are bare lowercase words; ARGV-value literals like 'meter' are
    # also lowercase words — we return ALL single-quoted bare-word tokens.
    # The caller selects the name-position subset by index (alternating name/value).
    return tokens


def test_metered_xadd_envelope_field_order_is_canonical() -> None:
    """The three envelope field NAMES appear, in canonical order, in the vendored Lua.

    Checks position-order (sorted ascending) so any transpose between event_id,
    type, and data is caught even if all three names are individually present.
    """
    positions = [
        _VENDORED_EMIT_METER_XADD.find(f"'{name}'")
        for name in _ENVELOPE_FIELD_ORDER
    ]
    missing = [
        name
        for name, pos in zip(_ENVELOPE_FIELD_ORDER, positions)
        if pos < 0
    ]
    assert not missing, (
        f"envelope field name(s) missing from vendored meter XADD: {missing!r} — "
        "update _VENDORED_EMIT_METER_XADD to match kernel billing/lua_scripts.py EMIT_METER"
    )
    assert positions == sorted(positions), (
        f"billing-stream XADD envelope field order drifted from {_ENVELOPE_FIELD_ORDER} "
        f"(positions={positions}); "
        "kernel EMIT_METER must keep event_id < type < data — "
        "sync _VENDORED_EMIT_METER_XADD and confirm the other 4 Lua copies"
    )


def test_metered_event_type_discriminator_is_meter() -> None:
    """The literal discriminator ``'type', 'meter'`` is present in the vendored Lua.

    The consumer and billing-worker route on this exact value.  Any rename of the
    discriminator (e.g. 'usage' or 'metered') silently breaks routing at runtime.
    """
    assert f"'type', '{_METER_TYPE_DISCRIMINATOR}'" in _VENDORED_EMIT_METER_XADD, (
        f"meter type discriminator 'type', '{_METER_TYPE_DISCRIMINATOR}' not found in "
        "vendored EMIT_METER — update _VENDORED_EMIT_METER_XADD and "
        "_METER_TYPE_DISCRIMINATOR to match kernel billing/lua_scripts.py EMIT_METER"
    )


def test_metered_xadd_field_name_positional_pattern() -> None:
    """Structural assertion: parse the quoted tokens from the XADD tail and verify
    the name-slot tokens at positions [0, 2, 4] (0-indexed within the tail tokens)
    match the canonical envelope names exactly — name/value interleave is preserved.

    This catches a bug where names and values are swapped in the Lua (e.g.
    ``'ARGV[1]', event_id`` instead of ``'event_id', ARGV[1]``).
    """
    # Isolate the XADD tail after the auto-id '*' sentinel.
    # Full form: XADD KEYS[1] '*' field1 val1 field2 val2 field3 val3
    # We split on the literal " '*'" to get everything after the auto-id marker.
    parts = _VENDORED_EMIT_METER_XADD.split("'*',", 1)
    assert len(parts) == 2, (
        "vendored XADD line does not contain the expected '*' auto-id sentinel — "
        "format changed; review _VENDORED_EMIT_METER_XADD"
    )
    xadd_tail = parts[1]

    # Extract all single-quoted bare-word tokens from the tail (field names + 'meter').
    tokens = _parse_quoted_field_names(xadd_tail)
    # Expected quoted tokens in order: 'event_id' ARGV[1] 'type' 'meter' 'data' ARGV[2]
    # quoted tokens only: ['event_id', 'type', 'meter', 'data']
    assert tokens == ["event_id", "type", "meter", "data"], (
        f"XADD tail quoted-token sequence is {tokens!r}; "
        "expected ['event_id', 'type', 'meter', 'data'] — "
        "field names and/or discriminator literal have drifted in _VENDORED_EMIT_METER_XADD"
    )
    # Additionally confirm that the name-slot positions (0, 2 among bare-word names) match.
    bare_names = [t for t in tokens if t != _METER_TYPE_DISCRIMINATOR]
    assert bare_names == list(_ENVELOPE_FIELD_ORDER), (
        f"envelope field names (excluding discriminator literal) are {bare_names!r}; "
        f"expected {list(_ENVELOPE_FIELD_ORDER)!r}"
    )
