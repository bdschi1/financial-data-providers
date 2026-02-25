"""Tests for DataProvider and MarketDataProvider ABCs."""

from __future__ import annotations

import pytest
from abc import ABC
from datetime import date, timedelta

import polars as pl

from bds_data_providers import DataProvider, MarketDataProvider


class TestDataProviderABC:
    """DataProvider (Polars) ABC contract tests."""

    def test_is_abstract(self):
        assert issubclass(DataProvider, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            DataProvider()

    def test_required_methods(self):
        methods = {"fetch_daily_prices", "fetch_ticker_info",
                   "fetch_current_prices", "fetch_risk_free_rate"}
        abstract = {m for m in dir(DataProvider) if getattr(getattr(DataProvider, m), "__isabstractmethod__", False)}
        assert methods <= abstract

    def test_name_property_has_default(self):
        """Subclass that implements all abstract methods should get default name."""
        class Dummy(DataProvider):
            def fetch_daily_prices(self, tickers, start, end): ...
            def fetch_ticker_info(self, ticker): ...
            def fetch_current_prices(self, tickers): ...
            def fetch_risk_free_rate(self): ...

        d = Dummy()
        assert d.name == "Dummy"

    def test_fetch_price_history_is_concrete(self):
        """fetch_price_history should NOT be abstract — it's a convenience method."""
        abstract = {
            m for m in dir(DataProvider)
            if getattr(getattr(DataProvider, m), "__isabstractmethod__", False)
        }
        assert "fetch_price_history" not in abstract

    def test_fetch_price_history_delegates_to_fetch_daily_prices(self):
        """Convenience method should delegate and convert format."""
        today = date.today()

        class StubProvider(DataProvider):
            def fetch_daily_prices(self, tickers, start, end):
                return pl.DataFrame({
                    "date": [today - timedelta(days=2), today - timedelta(days=1)],
                    "ticker": ["AAPL", "AAPL"],
                    "open": [100.0, 101.0],
                    "high": [102.0, 103.0],
                    "low": [99.0, 100.0],
                    "close": [101.0, 102.0],
                    "volume": [1e6, 1.1e6],
                }).with_columns(pl.col("date").cast(pl.Date))

            def fetch_ticker_info(self, ticker):
                return {}

            def fetch_current_prices(self, tickers):
                return {}

            def fetch_risk_free_rate(self):
                return 0.05

        p = StubProvider()
        rows = p.fetch_price_history("AAPL", days=5)
        assert len(rows) == 2
        assert rows[0]["close"] == 101.0
        assert rows[1]["close"] == 102.0
        assert set(rows[0].keys()) == {"date", "open", "high", "low", "close", "volume"}

    def test_fetch_price_history_returns_empty_on_failure(self):
        """Convenience method should return [] if fetch_daily_prices raises."""
        class FailProvider(DataProvider):
            def fetch_daily_prices(self, tickers, start, end):
                raise RuntimeError("network error")

            def fetch_ticker_info(self, ticker):
                return {}

            def fetch_current_prices(self, tickers):
                return {}

            def fetch_risk_free_rate(self):
                return 0.05

        p = FailProvider()
        assert p.fetch_price_history("AAPL") == []

    def test_fetch_price_history_filters_by_ticker(self):
        """Should only return rows for the requested ticker."""
        today = date.today()

        class MultiProvider(DataProvider):
            def fetch_daily_prices(self, tickers, start, end):
                return pl.DataFrame({
                    "date": [today, today],
                    "ticker": ["AAPL", "MSFT"],
                    "open": [100.0, 200.0],
                    "high": [102.0, 205.0],
                    "low": [99.0, 198.0],
                    "close": [101.0, 203.0],
                    "volume": [1e6, 2e6],
                }).with_columns(pl.col("date").cast(pl.Date))

            def fetch_ticker_info(self, ticker):
                return {}

            def fetch_current_prices(self, tickers):
                return {}

            def fetch_risk_free_rate(self):
                return 0.05

        p = MultiProvider()
        rows = p.fetch_price_history("MSFT", days=5)
        assert len(rows) == 1
        assert rows[0]["close"] == 203.0


class TestMarketDataProviderABC:
    """MarketDataProvider (dict/pandas) ABC contract tests."""

    def test_is_abstract(self):
        assert issubclass(MarketDataProvider, ABC)

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            MarketDataProvider()

    def test_required_methods(self):
        methods = {"get_ticker_object", "get_company_overview",
                   "get_price_data", "get_fundamentals", "get_info",
                   "get_insider_transactions", "get_earnings_history",
                   "get_quarterly_earnings", "get_history"}
        abstract = {m for m in dir(MarketDataProvider) if getattr(getattr(MarketDataProvider, m), "__isabstractmethod__", False)}
        assert methods <= abstract

    def test_name_property_has_default(self):
        class Dummy(MarketDataProvider):
            def get_ticker_object(self, ticker): ...
            def get_company_overview(self, ticker): ...
            def get_price_data(self, ticker, period="6mo"): ...
            def get_fundamentals(self, ticker): ...
            def get_info(self, ticker): ...
            def get_insider_transactions(self, ticker): ...
            def get_earnings_history(self, ticker): ...
            def get_quarterly_earnings(self, ticker): ...
            def get_history(self, ticker, period="6mo"): ...

        d = Dummy()
        assert d.name == "Dummy"
