<!-- financial-data-providers/README.md | Last updated: 2026-06-13 -->

# bds-data-providers

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![tests](https://img.shields.io/badge/tests-139%20passing-brightgreen?style=flat)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

A shared package giving every repo in the ecosystem one consistent interface for market data — Yahoo Finance, Alpha Vantage, Bloomberg, and Interactive Brokers — with the same provider logic, fallback behavior, and optional Bloomberg/IB path.

**Plain English:** Instead of each project writing its own data-fetching code, they install this package and get the same providers and the same safe fallback. Used by `backtest-lab`, `ls-portfolio-lab`, `multi-agent-investment-committee`, and `fund-tracker-13f`.

## Install

```
pip install -e "."             # base (Yahoo)
pip install -e ".[bloomberg]"  # or .[ibkr], .[alphavantage], .[all]
pip install -e ".[dev]"        # pytest, ruff
```

From another repo: `bds-data-providers @ git+https://github.com/bdschi1/financial-data-providers.git`

## Two ABCs

- **`DataProvider`** (Polars-native) — bulk time-series; used by backtest-lab, ls-portfolio-lab, fund-tracker-13f. `get_provider()` / `get_provider_safe()`.
- **`MarketDataProvider`** (dict/pandas) — agent tool layer; used by multi-agent-investment-committee. `get_market_provider()` / `get_market_provider_safe()`.

The `*_safe()` factories never raise — they fall back to Yahoo on any failure.

```python
from bds_data_providers import get_provider
from datetime import date

df = get_provider().fetch_daily_prices(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 12, 31))
```

## Providers

| Provider | Cost | Latency | Requires |
|---|---|---|---|
| Yahoo Finance | Free | EOD (~18h) | `yfinance` (base) |
| Alpha Vantage | Free / paid | EOD → real-time | `requests` + `ALPHAVANTAGE_API_KEY` |
| Bloomberg | Terminal license | Real-time | `blpapi` + Terminal / B-PIPE |
| Interactive Brokers | Brokerage account | Real-time | `ib_insync` + TWS / Gateway |

Yahoo is always the default; the rest are auto-detected when their package is importable and the service is reachable.

## Tests

```
pytest tests/ -v
```

## License

MIT
