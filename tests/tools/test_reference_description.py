# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""B1 — every symbol carries a ``description`` field (str, ``""`` when no doc)."""
from imperal_sdk.devtools.generate_reference import generate_reference


def test_symbols_carry_description():
    syms = generate_reference()["symbols"]
    # A ui component with a docstring carries it; a None-doc symbol degrades to "".
    assert "description" in next(iter(syms.values()))
    assert all(isinstance(s.get("description", ""), str) for s in syms.values())


def test_description_is_always_str_not_none():
    """Degrade path must produce "" not None when __doc__ is absent."""
    syms = generate_reference()["symbols"]
    for name, sym in syms.items():
        assert isinstance(sym["description"], str), (
            f"{name!r}: description is {sym['description']!r}, expected str"
        )


def test_description_is_stripped():
    """Descriptions must not carry leading/trailing whitespace."""
    syms = generate_reference()["symbols"]
    for name, sym in syms.items():
        desc = sym["description"]
        assert desc == desc.strip(), (
            f"{name!r}: description has surrounding whitespace"
        )
