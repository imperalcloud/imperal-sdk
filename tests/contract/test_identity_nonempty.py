# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the Apache-2.0 License. See LICENSE file for details.
"""T15: UserContext.imperal_id / tenant_id must be non-empty (min_length=1).
agency_id stays nullable with NO min_length constraint (B2B known-gap).
"""
import pytest
from pydantic import ValidationError

from imperal_sdk.types.identity import UserContext


def test_empty_imperal_id_rejected():
    with pytest.raises(ValidationError):
        UserContext(imperal_id="", tenant_id="t1", email="e", role="user")


def test_empty_tenant_id_rejected():
    with pytest.raises(ValidationError):
        UserContext(imperal_id="u1", tenant_id="", email="e", role="user")


def test_agency_id_still_optional_and_none_ok():
    # agency_id is nullable with known B2B gap — None must remain valid (no min_length)
    UserContext(imperal_id="u1", tenant_id="t1", email="e", role="user", agency_id=None)
