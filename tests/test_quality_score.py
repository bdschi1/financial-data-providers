"""Tests for per-provider quality_score()."""

from __future__ import annotations

from bds_data_providers.alphavantage_market import AlphaVantageMarketProvider
from bds_data_providers.market_data_provider import MarketDataProvider
from bds_data_providers.provider import DataProvider
from bds_data_providers.yahoo import YahooProvider
from bds_data_providers.yahoo_market import YahooMarketProvider


def test_abc_default_is_midpoint():
    class _Stub(DataProvider):
        def fetch_daily_prices(self, tickers, start, end): ...
        def fetch_ticker_info(self, ticker): ...
        def fetch_current_prices(self, tickers): ...
        def fetch_risk_free_rate(self): ...

    assert _Stub().quality_score() == 0.5


def test_market_abc_default_is_midpoint():
    class _Stub(MarketDataProvider):
        def get_ticker_object(self, ticker): ...
        def get_company_overview(self, ticker): ...
        def get_price_data(self, ticker, period="6mo"): ...
        def get_fundamentals(self, ticker): ...
        def get_info(self, ticker): ...
        def get_insider_transactions(self, ticker): ...
        def get_earnings_history(self, ticker): ...
        def get_quarterly_earnings(self, ticker): ...
        def get_history(self, ticker, period="6mo"): ...

    assert _Stub().quality_score() == 0.5


def test_yahoo_score():
    assert YahooProvider().quality_score() == 0.55
    assert YahooMarketProvider().quality_score() == 0.55


def test_score_in_unit_interval():
    """All real provider scores must be in [0, 1]."""
    score = YahooProvider().quality_score()
    assert 0.0 <= score <= 1.0


def test_alphavantage_requires_key_then_scores_0p6(monkeypatch):
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-key")
    provider = AlphaVantageMarketProvider()
    assert provider.quality_score() == 0.60
