"""Tests for Bloomberg field validator (_bbg_fields.py)."""

from __future__ import annotations

import pytest

from bds_data_providers._bbg_fields import (
    UnknownBloombergField,
    is_known_field,
    known_fields,
    register_fields,
    validate_fields,
)


def test_known_price_fields_validate():
    validate_fields(["PX_LAST", "PX_OPEN", "VOLUME", "BID", "ASK"])


def test_unknown_field_raises():
    with pytest.raises(UnknownBloombergField) as exc:
        validate_fields(["PX_LAST", "NOT_A_REAL_FIELD"])
    assert "NOT_A_REAL_FIELD" in str(exc.value)


def test_multiple_unknown_fields_all_reported():
    with pytest.raises(UnknownBloombergField) as exc:
        validate_fields(["BOGUS_ONE", "BOGUS_TWO"])
    msg = str(exc.value)
    assert "BOGUS_ONE" in msg
    assert "BOGUS_TWO" in msg


def test_is_known_field():
    assert is_known_field("PX_LAST")
    assert not is_known_field("NOT_A_FIELD")


def test_register_fields_adds_to_whitelist():
    assert not is_known_field("CUSTOM_FIELD")
    register_fields(["CUSTOM_FIELD"])
    assert is_known_field("CUSTOM_FIELD")
    validate_fields(["CUSTOM_FIELD"])


def test_known_fields_returns_frozenset():
    kf = known_fields()
    assert isinstance(kf, frozenset)
    assert "PX_LAST" in kf


def test_empty_list_passes():
    validate_fields([])
