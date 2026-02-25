"""Abstract data provider interface (Polars-based).

Defines the contract for fetching market data as Polars DataFrames.
Used by backtest-lab and ls-portfolio-lab.

Extended with bid/ask and intraday volume support for execution realism.
Concrete implementations: yahoo.py, bloomberg.py, ib.py.

This ABC is independent of the MarketDataProvider ABC in
market_data_provider.py, which serves a different dict/pandas-based
interface for multi-agent-investment-committee.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import polars as pl


class DataProvider(ABC):
    """Abstract interface for market data providers.

    All providers return polars DataFrames in long format.
    Columns use lowercase snake_case: date, ticker, open, high, low, close,
    adj_close, volume, bid, ask (bid/ask optional depending on provider).
    """

    @property
    def name(self) -> str:
        """Human-readable provider name (override in subclasses)."""
        return type(self).__name__

    @property
    def supports_bid_ask(self) -> bool:
        """Whether this provider returns bid/ask data.

        Yahoo Finance does not. Bloomberg and IB do.
        The engine uses this to decide which fill model is available.
        """
        return False

    @abstractmethod
    def fetch_daily_prices(
        self,
        tickers: list[str],
        start: date,
        end: date,
    ) -> pl.DataFrame:
        """Fetch daily OHLCV + adjusted close for a list of tickers.

        Returns long-format DataFrame with columns:
            date, ticker, open, high, low, close, adj_close, volume

        If the provider supports bid/ask, also includes:
            bid, ask

        Sorted by (ticker, date). Date column is pl.Date.
        """
        ...

    @abstractmethod
    def fetch_ticker_info(self, ticker: str) -> dict:
        """Fetch fundamental info for a single ticker.

        Returns dict with standardized keys:
            market_cap, sector, industry, beta, shares_outstanding,
            avg_volume, dividend_yield, short_pct_of_float
        """
        ...

    @abstractmethod
    def fetch_current_prices(self, tickers: list[str]) -> dict[str, float]:
        """Fetch latest closing price for a list of tickers.

        Returns: {ticker: price}
        """
        ...

    @abstractmethod
    def fetch_risk_free_rate(self) -> float:
        """Fetch current annualized risk-free rate.

        Uses 13-week T-bill rate (^IRX) by default.
        Returns as decimal (e.g., 0.05 for 5%).
        """
        ...

    # ------------------------------------------------------------------
    # Convenience methods (concrete — delegate to abstract methods)
    # ------------------------------------------------------------------

    def fetch_price_history(self, ticker: str, days: int = 400) -> list[dict]:
        """Single-ticker price history as list of dicts.

        Convenience wrapper around fetch_daily_prices() for consumers that
        need one ticker at a time in dict format (e.g. fund-tracker-13f).

        Returns list of dicts with keys: date, open, high, low, close, volume.
        Sorted oldest → newest.  Returns [] on failure.
        """
        from datetime import timedelta

        end = date.today()
        start = end - timedelta(days=days)
        try:
            df = self.fetch_daily_prices([ticker], start, end)
        except Exception:
            return []
        rows = df.filter(pl.col("ticker") == ticker).sort("date")
        return [
            {
                "date": r["date"],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
            }
            for r in rows.iter_rows(named=True)
        ]
