"""Tests for YahooProvider (DataProvider ABC - Polars)."""

from __future__ import annotations

import pytest
from datetime import date

import polars as pl

from bds_data_providers import YahooProvider, DataProvider


class TestYahooProvider:
    """YahooProvider implements DataProvider correctly."""

    def test_is_data_provider(self):
        p = YahooProvider()
        assert isinstance(p, DataProvider)

    def test_name(self):
        p = YahooProvider()
        assert p.name == "Yahoo Finance"

    def test_empty_tickers_returns_empty_df(self):
        p = YahooProvider()
        df = p.fetch_daily_prices([], date(2024, 1, 1), date(2024, 1, 31))
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 0
        assert "date" in df.columns
        assert "ticker" in df.columns
        assert "close" in df.columns

    def test_fetch_ticker_info_returns_dict(self):
        """Info should always return dict with expected keys, even on failure."""
        p = YahooProvider()
        # Use a deliberately invalid ticker to test fallback
        info = p.fetch_ticker_info("ZZZZZZZZZ")
        assert isinstance(info, dict)
        assert "market_cap" in info
        assert "sector" in info
        assert "beta" in info

    def test_empty_current_prices(self):
        p = YahooProvider()
        prices = p.fetch_current_prices([])
        assert isinstance(prices, dict)
        assert len(prices) == 0

    def test_risk_free_rate_returns_float(self):
        p = YahooProvider()
        rate = p.fetch_risk_free_rate()
        assert isinstance(rate, float)
        assert 0.0 <= rate <= 0.20  # reasonable range


class TestYahooProviderSchema:
    """Verify DataFrame schema from fetch_daily_prices."""

    def test_schema_columns_present(self):
        p = YahooProvider()
        df = p.fetch_daily_prices([], date(2024, 1, 1), date(2024, 1, 31))
        expected = {"date", "ticker", "open", "high", "low", "close", "adj_close", "volume"}
        assert expected <= set(df.columns)
