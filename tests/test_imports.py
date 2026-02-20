"""Test that all public imports work and __all__ is correct."""

from __future__ import annotations


def test_top_level_imports():
    """All public names importable from bds_data_providers."""
    from bds_data_providers import (
        DataProvider,
        MarketDataProvider,
        YahooProvider,
        BloombergProvider,
        IBProvider,
        AlphaVantageProvider,
        YahooMarketProvider,
        BloombergMarketProvider,
        IBMarketProvider,
        AlphaVantageMarketProvider,
        get_provider,
        get_provider_safe,
        available_providers,
        get_market_provider,
        get_market_provider_safe,
        available_market_providers,
    )


def test_all_exports_match():
    """__all__ should contain all public names."""
    import bds_data_providers
    expected = {
        "DataProvider", "MarketDataProvider",
        "YahooProvider", "BloombergProvider", "IBProvider", "AlphaVantageProvider",
        "YahooMarketProvider", "BloombergMarketProvider", "IBMarketProvider",
        "AlphaVantageMarketProvider",
        "get_provider", "get_provider_safe", "available_providers",
        "get_market_provider", "get_market_provider_safe", "available_market_providers",
    }
    actual = set(bds_data_providers.__all__)
    assert expected == actual


def test_submodule_imports():
    """Individual submodules importable."""
    import bds_data_providers.provider
    import bds_data_providers.market_data_provider
    import bds_data_providers.yahoo
    import bds_data_providers.bloomberg
    import bds_data_providers.ib
    import bds_data_providers.factory
    import bds_data_providers.yahoo_market
    import bds_data_providers.bloomberg_market
    import bds_data_providers.ib_market
    import bds_data_providers.alphavantage
    import bds_data_providers.alphavantage_market
    import bds_data_providers.market_factory
