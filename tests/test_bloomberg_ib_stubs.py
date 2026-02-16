"""Tests for Bloomberg and IB providers when their deps are NOT installed.

These tests verify that is_available() returns False and that the providers
gracefully handle missing dependencies.
"""

from __future__ import annotations

import pytest

from bds_data_providers.bloomberg import is_available as bbg_available
from bds_data_providers.ib import is_available as ib_available
from bds_data_providers.bloomberg_market import is_available as bbg_market_available
from bds_data_providers.ib_market import is_available as ib_market_available


class TestBloombergNotInstalled:
    """Bloomberg provider when blpapi is not installed."""

    def test_is_not_available(self):
        # blpapi is not installed in this test env
        assert bbg_available() is False

    def test_market_not_available(self):
        assert bbg_market_available() is False

    def test_instantiation_raises(self):
        from bds_data_providers.bloomberg import BloombergProvider
        with pytest.raises(ImportError, match="blpapi"):
            BloombergProvider()

    def test_market_instantiation_raises(self):
        from bds_data_providers.bloomberg_market import BloombergMarketProvider
        with pytest.raises(ImportError, match="blpapi"):
            BloombergMarketProvider()


class TestIBNotInstalled:
    """IB provider when ib_insync is not installed."""

    def test_is_not_available(self):
        # ib_insync is not installed in this test env
        assert ib_available() is False

    def test_market_not_available(self):
        assert ib_market_available() is False

    def test_instantiation_raises(self):
        from bds_data_providers.ib import IBProvider
        with pytest.raises(ImportError, match="ib_insync"):
            IBProvider()

    def test_market_instantiation_raises(self):
        from bds_data_providers.ib_market import IBMarketProvider
        with pytest.raises(ImportError, match="ib_insync"):
            IBMarketProvider()
