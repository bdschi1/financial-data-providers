"""Tests for DataProvider and MarketDataProvider ABCs."""

from __future__ import annotations

import pytest
from abc import ABC
from datetime import date

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
