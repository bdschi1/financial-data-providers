# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] - 2026-02-15

### Added
- `DataProvider` ABC (Polars-native) with `fetch_daily_prices`, `fetch_ticker_info`, `fetch_current_prices`, `fetch_risk_free_rate`, and bid/ask support flag
- `MarketDataProvider` ABC (dict/pandas) with 9 methods: `get_ticker_object`, `get_company_overview`, `get_price_data`, `get_fundamentals`, `get_info`, `get_insider_transactions`, `get_earnings_history`, `get_quarterly_earnings`, `get_history`
- Four provider implementations: Yahoo Finance, Alpha Vantage, Bloomberg, Interactive Brokers (each with both Polars and dict/pandas variants)
- Factory functions with auto-detection, singleton caching, and safe fallback to Yahoo: `get_provider()`, `get_market_provider()`, `get_provider_safe()`, `get_market_provider_safe()`
- `available_providers()` and `available_market_providers()` for runtime discovery
- Optional dependency groups: `bloomberg`, `ibkr`, `alphavantage`, `all`, `dev`
- Full test suite: ABC contract tests, factory tests, import/export tests, Yahoo implementation tests, Bloomberg/IB stub tests
