"""Tests for provider factories."""

from __future__ import annotations

import pytest

from bds_data_providers import (
    DataProvider,
    MarketDataProvider,
    YahooProvider,
    YahooMarketProvider,
    get_provider,
    get_provider_safe,
    available_providers,
    get_market_provider,
    get_market_provider_safe,
    available_market_providers,
)
from bds_data_providers.factory import clear_cache
from bds_data_providers.market_factory import clear_cache as clear_market_cache


class TestDataProviderFactory:
    """Tests for DataProvider (Polars) factory."""

    def setup_method(self):
        clear_cache()

    def test_available_always_includes_yahoo(self):
        providers = available_providers()
        assert "Yahoo Finance" in providers

    def test_get_default_returns_yahoo(self):
        p = get_provider()
        assert isinstance(p, YahooProvider)
        assert isinstance(p, DataProvider)
        assert p.name == "Yahoo Finance"

    def test_get_yahoo_by_name(self):
        p = get_provider("Yahoo Finance")
        assert isinstance(p, YahooProvider)

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("NonExistentProvider")

    def test_safe_fallback(self):
        p = get_provider_safe("NonExistentProvider")
        assert isinstance(p, YahooProvider)

    def test_caching(self):
        p1 = get_provider()
        p2 = get_provider()
        assert p1 is p2

    def test_clear_cache_allows_new_instance(self):
        p1 = get_provider()
        clear_cache()
        p2 = get_provider()
        # After clearing cache, a new instance is created
        assert p1 is not p2


class TestMarketDataProviderFactory:
    """Tests for MarketDataProvider (dict/pandas) factory."""

    def setup_method(self):
        clear_market_cache()

    def test_available_always_includes_yahoo(self):
        providers = available_market_providers()
        assert "Yahoo Finance" in providers

    def test_get_default_returns_yahoo(self):
        p = get_market_provider()
        assert isinstance(p, YahooMarketProvider)
        assert isinstance(p, MarketDataProvider)
        assert p.name == "Yahoo Finance"

    def test_get_yahoo_by_name(self):
        p = get_market_provider("Yahoo Finance")
        assert isinstance(p, YahooMarketProvider)

    def test_get_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_market_provider("NonExistentProvider")

    def test_safe_fallback(self):
        p = get_market_provider_safe("NonExistentProvider")
        assert isinstance(p, YahooMarketProvider)

    def test_caching(self):
        p1 = get_market_provider()
        p2 = get_market_provider()
        assert p1 is p2
