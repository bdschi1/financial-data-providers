"""Alpha Vantage data provider -- concrete implementation of DataProvider.

Uses the Alpha Vantage REST API for market data. Requires an API key
(free or premium) set via ALPHAVANTAGE_API_KEY environment variable.

Strengths over Yahoo Finance:
    - Structured fundamental data (income statement, balance sheet, cash flow)
    - Reliable earnings with estimates/actuals/surprises
    - Proper Treasury Yield endpoint for risk-free rate
    - Stable REST API vs yfinance's web scraping

Limitations:
    - Rate-limited: free tier = 25 requests/day, premium varies
    - One ticker per request (no batch download)
    - No insider transactions, no options data

Does NOT provide bid/ask -- same mid-price fill behavior as Yahoo.

Resilience: all API calls are wrapped with tenacity retry (exponential
backoff: 2s -> 4s -> 8s, 3 attempts) matching the Yahoo provider pattern.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import polars as pl
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bds_data_providers.provider import DataProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import -- requests is used for API calls
# ---------------------------------------------------------------------------

try:
    import requests

    _HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore[assignment]
    _HAS_REQUESTS = False


def is_available() -> bool:
    """Return True if requests is installed and API key is set."""
    return _HAS_REQUESTS and bool(os.environ.get("ALPHAVANTAGE_API_KEY"))


# ---------------------------------------------------------------------------
# Retry decorator -- exponential backoff 2s->4s->8s, 3 attempts
# ---------------------------------------------------------------------------

_av_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((Exception,)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

_AV_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageProvider(DataProvider):
    """Fetch market data from Alpha Vantage REST API.

    Args:
        api_key: Alpha Vantage API key. If not provided, reads from
                 ALPHAVANTAGE_API_KEY environment variable.
    """

    def __init__(self, api_key: str | None = None):
        if not _HAS_REQUESTS:
            raise ImportError("requests is required: pip install requests")
        self._api_key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Alpha Vantage API key required. Set ALPHAVANTAGE_API_KEY "
                "environment variable or pass api_key parameter."
            )
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return "Alpha Vantage"

    @property
    def supports_bid_ask(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Low-level API helper
    # ------------------------------------------------------------------

    @_av_retry
    def _api_call(self, params: dict[str, str]) -> dict[str, Any]:
        """Execute an Alpha Vantage API request with retry."""
        params["apikey"] = self._api_key
        resp = self._session.get(_AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # AV returns error messages in JSON body, not HTTP status
        if "Error Message" in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        if "Note" in data:
            # Rate limit hit
            logger.warning("Alpha Vantage rate limit: %s", data["Note"])
            raise RuntimeError(f"Rate limited: {data['Note']}")
        if "Information" in data and "rate" in data.get("Information", "").lower():
            logger.warning("Alpha Vantage rate limit: %s", data["Information"])
            raise RuntimeError(f"Rate limited: {data['Information']}")

        return data

    # ------------------------------------------------------------------
    # DataProvider interface
    # ------------------------------------------------------------------

    def fetch_daily_prices(
        self,
        tickers: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        """Fetch daily OHLCV + adjusted close for multiple tickers.

        Uses TIME_SERIES_DAILY_ADJUSTED endpoint (one ticker at a time).
        Returns long-format DataFrame: date, ticker, open, high, low, close,
        adj_close, volume.
        """
        empty_schema = {
            "date": pl.Date,
            "ticker": pl.Utf8,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "adj_close": pl.Float64,
            "volume": pl.Float64,
        }

        if not tickers:
            return pl.DataFrame(schema=empty_schema)

        logger.info(
            "Fetching AV prices for %d tickers: %s to %s",
            len(tickers), start.isoformat(), end.isoformat(),
        )

        frames: list[pl.DataFrame] = []
        for ticker in tickers:
            try:
                df = self._fetch_single_daily(ticker, start, end)
                if df is not None and len(df) > 0:
                    frames.append(df)
            except Exception:
                logger.exception("AV price fetch failed for %s", ticker)

        if not frames:
            return pl.DataFrame(schema=empty_schema)

        result = pl.concat(frames, how="diagonal")
        return result.sort(["ticker", "date"])

    def _fetch_single_daily(
        self, ticker: str, start: date, end: date
    ) -> pl.DataFrame | None:
        """Fetch daily adjusted prices for a single ticker."""
        data = self._api_call({
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": ticker,
            "outputsize": "full",
            "datatype": "json",
        })

        ts_key = "Time Series (Daily)"
        if ts_key not in data:
            logger.warning("No daily data in AV response for %s", ticker)
            return None

        rows: list[dict[str, Any]] = []
        for date_str, bar in data[ts_key].items():
            bar_date = date.fromisoformat(date_str)
            if bar_date < start or bar_date > end:
                continue
            rows.append({
                "date": bar_date,
                "ticker": ticker,
                "open": float(bar["1. open"]),
                "high": float(bar["2. high"]),
                "low": float(bar["3. low"]),
                "close": float(bar["4. close"]),
                "adj_close": float(bar["5. adjusted close"]),
                "volume": float(bar["6. volume"]),
            })

        if not rows:
            return None

        return pl.DataFrame(rows).with_columns(pl.col("date").cast(pl.Date))

    def fetch_ticker_info(self, ticker: str) -> dict:
        """Fetch fundamental info using the OVERVIEW endpoint.

        Returns dict with standardized keys matching the DataProvider schema.
        """
        try:
            data = self._api_call({
                "function": "OVERVIEW",
                "symbol": ticker,
            })
        except Exception:
            logger.exception("AV overview fetch failed for %s", ticker)
            return {
                "market_cap": 0.0,
                "sector": "",
                "industry": "",
                "beta": 1.0,
                "shares_outstanding": 0,
                "avg_volume": 0,
                "dividend_yield": 0.0,
                "short_pct_of_float": 0.0,
            }

        return {
            "market_cap": _safe_float(data, "MarketCapitalization"),
            "sector": data.get("Sector", "") or "",
            "industry": data.get("Industry", "") or "",
            "beta": _safe_float(data, "Beta", 1.0),
            "shares_outstanding": int(_safe_float(data, "SharesOutstanding")),
            "avg_volume": 0,  # Not in OVERVIEW; would need separate call
            "dividend_yield": _safe_float(data, "DividendYield"),
            "short_pct_of_float": _safe_float(data, "ShortPercentFloat") / 100.0
            if data.get("ShortPercentFloat") and data["ShortPercentFloat"] != "None"
            else 0.0,
        }

    def fetch_current_prices(self, tickers: list[str]) -> dict[str, float]:
        """Fetch latest price for each ticker using GLOBAL_QUOTE."""
        prices: dict[str, float] = {}
        if not tickers:
            return prices

        for ticker in tickers:
            try:
                data = self._api_call({
                    "function": "GLOBAL_QUOTE",
                    "symbol": ticker,
                })
                quote = data.get("Global Quote", {})
                price = float(quote.get("05. price", 0))
                if price > 0:
                    prices[ticker] = price
            except Exception:
                logger.warning("AV current price failed for %s", ticker)

        return prices

    def fetch_risk_free_rate(self) -> float:
        """Fetch 3-month Treasury yield from Alpha Vantage TREASURY_YIELD.

        Returns as decimal (e.g., 0.05 for 5%).
        Falls back to 0.05 if unavailable.
        """
        try:
            data = self._api_call({
                "function": "TREASURY_YIELD",
                "interval": "daily",
                "maturity": "3month",
            })
            points = data.get("data", [])
            if points:
                # Most recent data point
                value = points[0].get("value")
                if value and value != ".":
                    return float(value) / 100.0
        except Exception:
            logger.warning("AV Treasury yield fetch failed, using 0.05 default")

        return 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(data: dict, key: str, default: float = 0.0) -> float:
    """Safely extract a float from an AV response dict."""
    val = data.get(key)
    if val is None or val == "None" or val == "-" or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
