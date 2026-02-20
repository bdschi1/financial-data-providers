"""bds-data-providers -- shared market data abstraction layer.

Exposes TWO independent ABCs for two different repo families:

1. ``DataProvider`` (Polars-based, 4 methods)
   Used by: backtest-lab, ls-portfolio-lab
   Factory: ``get_provider()``, ``get_provider_safe()``, ``available_providers()``

2. ``MarketDataProvider`` (dict/pandas-based, 9 methods)
   Used by: multi-agent-investment-committee
   Factory: ``get_market_provider()``, ``get_market_provider_safe()``,
            ``available_market_providers()``

Each ABC has three concrete implementations:
    - Yahoo Finance  (free, always available)
    - Bloomberg      (requires blpapi + Terminal/B-PIPE)
    - Interactive Brokers (requires ib_insync + TWS/Gateway)

Quick start (Polars ABC):
    from bds_data_providers import get_provider
    provider = get_provider()           # Yahoo Finance
    provider = get_provider("Bloomberg")

Quick start (dict/pandas ABC):
    from bds_data_providers import get_market_provider
    provider = get_market_provider()    # Yahoo Finance
    provider = get_market_provider("Bloomberg")
"""

# --- Polars-based ABC (backtest-lab, ls-portfolio-lab) ---
from bds_data_providers.provider import DataProvider
from bds_data_providers.yahoo import YahooProvider
from bds_data_providers.bloomberg import BloombergProvider
from bds_data_providers.ib import IBProvider
from bds_data_providers.alphavantage import AlphaVantageProvider
from bds_data_providers.factory import (
    get_provider,
    get_provider_safe,
    available_providers,
)

# --- dict/pandas-based ABC (multi-agent-investment-committee) ---
from bds_data_providers.market_data_provider import MarketDataProvider
from bds_data_providers.yahoo_market import YahooMarketProvider
from bds_data_providers.bloomberg_market import BloombergMarketProvider
from bds_data_providers.ib_market import IBMarketProvider
from bds_data_providers.alphavantage_market import AlphaVantageMarketProvider
from bds_data_providers.market_factory import (
    get_market_provider,
    get_market_provider_safe,
    available_market_providers,
)

__all__ = [
    # ABCs
    "DataProvider",
    "MarketDataProvider",
    # Polars providers
    "YahooProvider",
    "BloombergProvider",
    "IBProvider",
    "AlphaVantageProvider",
    # Polars factory
    "get_provider",
    "get_provider_safe",
    "available_providers",
    # dict/pandas providers
    "YahooMarketProvider",
    "BloombergMarketProvider",
    "IBMarketProvider",
    "AlphaVantageMarketProvider",
    # dict/pandas factory
    "get_market_provider",
    "get_market_provider_safe",
    "available_market_providers",
]
