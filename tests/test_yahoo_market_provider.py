"""Tests for YahooMarketProvider (MarketDataProvider ABC - dict/pandas)."""

from __future__ import annotations

import pytest

from bds_data_providers import YahooMarketProvider, MarketDataProvider
from bds_data_providers.yahoo_market import _format_large_number, _pct


class TestYahooMarketProvider:
    """YahooMarketProvider implements MarketDataProvider correctly."""

    def test_is_market_data_provider(self):
        p = YahooMarketProvider()
        assert isinstance(p, MarketDataProvider)

    def test_name(self):
        p = YahooMarketProvider()
        assert p.name == "Yahoo Finance"


class TestFormatHelpers:
    """Test shared formatting functions."""

    def test_format_large_number_trillion(self):
        assert _format_large_number(1.5e12) == "$1.50T"

    def test_format_large_number_billion(self):
        assert _format_large_number(230e9) == "$230.00B"

    def test_format_large_number_million(self):
        assert _format_large_number(45e6) == "$45.0M"

    def test_format_large_number_small(self):
        assert _format_large_number(1234) == "$1,234"

    def test_format_large_number_none(self):
        assert _format_large_number(None) is None

    def test_pct_converts(self):
        assert _pct(0.253) == "25.3%"

    def test_pct_none(self):
        assert _pct(None) is None

    def test_pct_zero(self):
        assert _pct(0.0) == "0.0%"
