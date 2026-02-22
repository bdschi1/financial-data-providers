# bds-data-providers

Shared market data provider package for the bds repo ecosystem. Extracts the data provider abstraction layer that was independently implemented in `ls-portfolio-lab`, `backtest-lab`, and `multi-agent-investment-committee` into a single installable package.

One package, two ABCs, four providers. Every repo in the ecosystem uses the same provider code, the same fallback logic, and the same Bloomberg/IB/Alpha Vantage integration path.

## Two ABCs

This package exposes two abstract base classes because the consuming repos have fundamentally different data needs:

### `DataProvider` (Polars-native)

Used by **backtest-lab** and **ls-portfolio-lab**. Designed for bulk time-series work where Polars DataFrames are the primary data structure.

Methods:
- `fetch_daily_prices(tickers, start, end) -> pl.DataFrame` -- OHLCV + adj_close, long format
- `fetch_ticker_info(ticker) -> dict` -- market_cap, sector, industry, beta, etc.
- `fetch_current_prices(tickers) -> dict[str, float]` -- latest close per ticker
- `fetch_risk_free_rate() -> float` -- annualized risk-free rate (13-week T-bill)

### `MarketDataProvider` (dict/pandas)

Used by **multi-agent-investment-committee**. Designed for the agent tool layer where each tool expects dicts or pandas DataFrames.

Methods:
- `get_ticker_object(ticker) -> Any` -- underlying ticker/session object
- `get_company_overview(ticker) -> dict` -- structured company profile
- `get_price_data(ticker, period) -> dict` -- price + performance metrics
- `get_fundamentals(ticker) -> dict` -- valuation, profitability, growth, balance sheet
- `get_info(ticker) -> dict` -- raw key-value info dict
- `get_insider_transactions(ticker) -> Any` -- insider buy/sell data
- `get_earnings_history(ticker) -> Any` -- earnings surprise history
- `get_quarterly_earnings(ticker) -> Any` -- quarterly revenue/earnings
- `get_history(ticker, period) -> Any` -- historical OHLCV as pandas DataFrame

## Four Providers

| Provider | Cost | Latency | Requirements |
|---|---|---|---|
| **Yahoo Finance** | Free | EOD (~18hr delay) | `yfinance` (included in base deps) |
| **Alpha Vantage** | Free / paid tiers | EOD (free) to real-time (paid) | `requests` + API key (`ALPHA_VANTAGE_API_KEY` env var) |
| **Bloomberg** | Terminal license | Real-time | `blpapi` + Bloomberg Terminal or B-PIPE |
| **Interactive Brokers** | Brokerage account | Real-time | `ib_insync` + TWS or IB Gateway running |

Yahoo is always the default. Alpha Vantage, Bloomberg, and IB are auto-detected based on whether their Python packages are importable and their services are reachable.

## Installation

From the repo root:

```bash
# Base install (Yahoo only)
pip install -e "."

# With Bloomberg support
pip install -e ".[bloomberg]"

# With Interactive Brokers support
pip install -e ".[ibkr]"

# Both optional providers
pip install -e ".[all]"

# Dev dependencies (pytest, ruff)
pip install -e ".[dev]"
```

## Usage

### DataProvider (Polars) -- for backtest-lab / ls-portfolio-lab

```python
from bds_data_providers import YahooProvider, get_provider
from datetime import date

# Direct instantiation
provider = YahooProvider()
df = provider.fetch_daily_prices(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 12, 31))
print(df)  # Polars DataFrame: date, ticker, open, high, low, close, adj_close, volume

# Factory (auto-detects available providers)
provider = get_provider()                    # Yahoo (default)
provider = get_provider("Bloomberg")         # Bloomberg (if blpapi installed)
provider = get_provider("Interactive Brokers")  # IB (if ib_insync installed)

# Fundamental data
info = provider.fetch_ticker_info("AAPL")
print(info["market_cap"], info["sector"])

# Current prices
prices = provider.fetch_current_prices(["AAPL", "MSFT", "GOOG"])
print(prices)  # {"AAPL": 185.50, "MSFT": 420.10, "GOOG": 175.25}

# Risk-free rate
rf = provider.fetch_risk_free_rate()
print(rf)  # 0.052
```

### MarketDataProvider (dict/pandas) -- for multi-agent-investment-committee

```python
from bds_data_providers import YahooMarketProvider, get_market_provider

# Direct instantiation
provider = YahooMarketProvider()
overview = provider.get_company_overview("AAPL")
print(overview["name"], overview["sector"], overview["market_cap_formatted"])

# Factory
provider = get_market_provider()                    # Yahoo (default)
provider = get_market_provider("Bloomberg")         # Bloomberg
provider = get_market_provider("Interactive Brokers")  # IB

# Price data with performance metrics
price_data = provider.get_price_data("AAPL", period="6mo")
print(price_data["current_price"], price_data["period_return_pct"])

# Fundamentals
fundamentals = provider.get_fundamentals("AAPL")
print(fundamentals["pe_trailing"], fundamentals["profit_margin"])

# Historical OHLCV (pandas DataFrame)
hist = provider.get_history("AAPL", period="1y")
print(hist.columns)  # Open, High, Low, Close, Volume
```

### Safe fallback (production use)

```python
from bds_data_providers import get_provider_safe, get_market_provider_safe

# Falls back to Yahoo if Bloomberg/IB connection fails
provider = get_provider_safe("Bloomberg")
market_provider = get_market_provider_safe("Bloomberg")
```

### Listing available providers

```python
from bds_data_providers import available_providers, available_market_providers

print(available_providers())         # ["Yahoo Finance", "Bloomberg"] (if blpapi installed)
print(available_market_providers())  # ["Yahoo Finance", "Bloomberg"]
```

## Architecture

```
bds-data-providers/
    pyproject.toml
    LICENSE
    README.md
    .gitignore
    bds_data_providers/
        __init__.py              # Public API re-exports
        provider.py              # DataProvider ABC (Polars)
        market_data_provider.py  # MarketDataProvider ABC (dict/pandas)
        factory.py               # get_provider(), get_provider_safe(), available_providers()
        market_factory.py        # get_market_provider(), get_market_provider_safe(), available_market_providers()
        yahoo.py                 # YahooProvider(DataProvider)
        yahoo_market.py          # YahooMarketProvider(MarketDataProvider)
        bloomberg.py             # BloombergProvider(DataProvider)
        bloomberg_market.py      # BloombergMarketProvider(MarketDataProvider)
        ib.py                    # IBProvider(DataProvider)
        ib_market.py             # IBMarketProvider(MarketDataProvider)
        alphavantage.py          # AlphaVantageProvider(DataProvider)
        alphavantage_market.py   # AlphaVantageMarketProvider(MarketDataProvider)
    tests/
        __init__.py
        test_provider_abc.py
        test_yahoo_provider.py
        test_yahoo_market_provider.py
        test_bloomberg_ib_stubs.py
        test_factory.py
        test_imports.py
```

## How Consuming Repos Integrate

### Step 1: Add editable install

In the consuming repo, add `bds-data-providers` as an editable dependency:

```bash
cd /path/to/ls-portfolio-lab
pip install -e /path/to/bds-data-providers
```

Or add to the consuming repo's `pyproject.toml`:

```toml
[project]
dependencies = [
    "bds-data-providers @ file:///path/to/bds-data-providers",
]
```

### Step 2: Update imports

**ls-portfolio-lab / backtest-lab** (before):
```python
from data.provider import DataProvider
from data.provider_factory import get_provider
from data.yahoo_provider import YahooProvider
```

**ls-portfolio-lab / backtest-lab** (after):
```python
from bds_data_providers import DataProvider, get_provider, YahooProvider
```

**multi-agent-investment-committee** (before):
```python
from tools.data_providers.base import MarketDataProvider
from tools.data_providers.factory import get_provider
from tools.data_providers.yahoo_provider import YahooProvider
```

**multi-agent-investment-committee** (after):
```python
from bds_data_providers import MarketDataProvider, get_market_provider, YahooMarketProvider
```

### Which Repo Uses Which ABC

| Repo | ABC | Factory function |
|---|---|---|
| `backtest-lab` | `DataProvider` | `get_provider()` |
| `ls-portfolio-lab` | `DataProvider` | `get_provider()` |
| `multi-agent-investment-committee` | `MarketDataProvider` | `get_market_provider()` |

## License

MIT

---

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat&logo=python&logoColor=white)

![Polars](https://img.shields.io/badge/Polars-CD792C?style=flat&logo=polars&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-150458?style=flat&logo=pandas&logoColor=white)
![Yahoo Finance](https://img.shields.io/badge/Yahoo_Finance-6001D2?style=flat&logo=yahoo&logoColor=white)
![Bloomberg](https://img.shields.io/badge/Bloomberg-000000?style=flat&logo=bloomberg&logoColor=white)
![Interactive Brokers](https://img.shields.io/badge/Interactive_Brokers-D71920?style=flat)
