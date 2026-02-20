"""Alpha Vantage data provider for MarketDataProvider (dict/pandas) ABC.

Wraps the Alpha Vantage REST API to implement the MarketDataProvider
interface. Requires ``requests`` and an API key set via
ALPHAVANTAGE_API_KEY environment variable.

Strengths over Yahoo Finance for MAIC:
    - Structured income statement / balance sheet / cash flow endpoints
    - Reliable earnings with estimates, actuals, and surprises
    - Stable API (vs yfinance web scraping that breaks periodically)
    - Better company overview data (sector, industry, description)

Used by multi-agent-investment-committee's tool layer.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import pandas as pd

from bds_data_providers.market_data_provider import MarketDataProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import
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
# Retry
# ---------------------------------------------------------------------------

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_av_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((Exception,)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

_AV_BASE_URL = "https://www.alphavantage.co/query"


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class AlphaVantageMarketProvider(MarketDataProvider):
    """Fetch market data from Alpha Vantage REST API.

    Implements the MarketDataProvider interface for use by
    multi-agent-investment-committee's tool layer. Returns the same
    dict schemas as YahooMarketProvider.

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
        # Cache overview data to avoid redundant API calls
        self._overview_cache: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "Alpha Vantage"

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

        if "Error Message" in data:
            raise ValueError(f"Alpha Vantage error: {data['Error Message']}")
        if "Note" in data:
            logger.warning("Alpha Vantage rate limit: %s", data["Note"])
            raise RuntimeError(f"Rate limited: {data['Note']}")
        if "Information" in data and "rate" in data.get("Information", "").lower():
            logger.warning("Alpha Vantage rate limit: %s", data["Information"])
            raise RuntimeError(f"Rate limited: {data['Information']}")

        return data

    def _get_overview(self, ticker: str) -> dict[str, Any]:
        """Fetch and cache the OVERVIEW endpoint for a ticker."""
        if ticker in self._overview_cache:
            return self._overview_cache[ticker]
        try:
            data = self._api_call({"function": "OVERVIEW", "symbol": ticker})
            self._overview_cache[ticker] = data
            return data
        except Exception as e:
            logger.error("AV overview failed for %s: %s", ticker, e)
            return {}

    # ------------------------------------------------------------------
    # MarketDataProvider interface
    # ------------------------------------------------------------------

    def get_ticker_object(self, ticker: str) -> Any:
        """Return a dict proxy (AV has no ticker object concept)."""
        return {"ticker": ticker, "provider": "alphavantage"}

    def get_company_overview(self, ticker: str) -> dict[str, Any]:
        """Get structured company overview from Alpha Vantage OVERVIEW."""
        try:
            ov = self._get_overview(ticker)
            mktcap = _safe_float(ov, "MarketCapitalization")
            return {
                "ticker": ticker,
                "name": ov.get("Name", ticker),
                "sector": ov.get("Sector", "Unknown"),
                "industry": ov.get("Industry", "Unknown"),
                "market_cap": mktcap,
                "market_cap_formatted": _format_large_number(mktcap),
                "currency": ov.get("Currency", "USD"),
                "exchange": ov.get("Exchange", "Unknown"),
                "description": (ov.get("Description", "") or "")[:500],
                "website": "",  # Not in AV OVERVIEW
                "employees": _safe_int(ov, "FullTimeEmployees"),
                "country": ov.get("Country", "Unknown"),
            }
        except Exception as e:
            logger.error("Failed to get company overview for %s: %s", ticker, e)
            return {"ticker": ticker, "error": str(e)}

    def get_price_data(self, ticker: str, period: str = "6mo") -> dict[str, Any]:
        """Get price data and performance metrics from Alpha Vantage."""
        try:
            hist = self.get_history(ticker, period)
            if hist.empty:
                return {"ticker": ticker, "error": "No price data available"}

            current_price = float(hist["Close"].iloc[-1])
            start_price = float(hist["Close"].iloc[0])
            high_52w = float(hist["Close"].max())
            low_52w = float(hist["Close"].min())
            avg_volume = int(hist["Volume"].mean())

            return {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "period_return_pct": round((current_price / start_price - 1) * 100, 2),
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "pct_from_high": round((current_price / high_52w - 1) * 100, 2),
                "pct_from_low": round((current_price / low_52w - 1) * 100, 2),
                "avg_daily_volume": avg_volume,
                "avg_volume_formatted": _format_large_number(avg_volume),
                "period": period,
                "data_points": len(hist),
            }
        except Exception as e:
            logger.error("Failed to get price data for %s: %s", ticker, e)
            return {"ticker": ticker, "error": str(e)}

    def get_fundamentals(self, ticker: str) -> dict[str, Any]:
        """Get fundamental financial data from Alpha Vantage.

        Combines OVERVIEW endpoint (ratios, margins) with
        INCOME_STATEMENT (revenue, net income, EBITDA) and
        BALANCE_SHEET (debt, cash, current ratio) for richer data
        than yfinance provides.
        """
        try:
            ov = self._get_overview(ticker)

            # Fetch income statement for revenue/EBITDA/net income
            income = self._get_income_statement(ticker)
            # Fetch balance sheet for debt/cash/current ratio
            balance = self._get_balance_sheet(ticker)

            # Latest annual figures
            latest_income = income[0] if income else {}
            latest_balance = balance[0] if balance else {}

            revenue = _safe_float(latest_income, "totalRevenue")
            ebitda = _safe_float(latest_income, "ebitda")
            net_income = _safe_float(latest_income, "netIncome")
            total_debt = (
                _safe_float(latest_balance, "shortTermDebt")
                + _safe_float(latest_balance, "longTermDebt")
            )
            total_cash = _safe_float(latest_balance, "cashAndShortTermInvestments")
            current_assets = _safe_float(latest_balance, "totalCurrentAssets")
            current_liabilities = _safe_float(latest_balance, "totalCurrentLiabilities")
            current_ratio = (
                round(current_assets / current_liabilities, 2)
                if current_liabilities > 0
                else None
            )

            # Revenue growth from last 2 annual reports
            revenue_growth = None
            if len(income) >= 2:
                prev_revenue = _safe_float(income[1], "totalRevenue")
                if prev_revenue > 0:
                    revenue_growth = f"{((revenue / prev_revenue) - 1) * 100:.1f}%"

            return {
                "ticker": ticker,
                # Valuation (from OVERVIEW)
                "pe_trailing": _safe_float_or_none(ov, "TrailingPE"),
                "pe_forward": _safe_float_or_none(ov, "ForwardPE"),
                "peg_ratio": _safe_float_or_none(ov, "PEGRatio"),
                "price_to_book": _safe_float_or_none(ov, "BookValue"),
                "price_to_sales": _safe_float_or_none(ov, "PriceToSalesRatioTTM"),
                "ev_to_ebitda": _safe_float_or_none(ov, "EVToEBITDA"),
                "ev_to_revenue": _safe_float_or_none(ov, "EVToRevenue"),
                # Profitability (from OVERVIEW)
                "profit_margin": _pct(ov, "ProfitMargin"),
                "operating_margin": _pct(ov, "OperatingMarginTTM"),
                "gross_margin": None,  # Not directly in OVERVIEW
                "roe": _pct(ov, "ReturnOnEquityTTM"),
                "roa": _pct(ov, "ReturnOnAssetsTTM"),
                # Growth
                "revenue_growth": revenue_growth,
                "earnings_growth": _pct(ov, "QuarterlyEarningsGrowthYOY"),
                # Income (from INCOME_STATEMENT)
                "revenue": revenue if revenue else None,
                "revenue_formatted": _format_large_number(revenue) if revenue else None,
                "ebitda": ebitda if ebitda else None,
                "ebitda_formatted": _format_large_number(ebitda) if ebitda else None,
                "net_income": net_income if net_income else None,
                # Balance sheet (from BALANCE_SHEET)
                "total_debt": total_debt if total_debt else None,
                "total_debt_formatted": _format_large_number(total_debt) if total_debt else None,
                "total_cash": total_cash if total_cash else None,
                "total_cash_formatted": _format_large_number(total_cash) if total_cash else None,
                "debt_to_equity": _safe_float_or_none(ov, "DebtToEquityRatio") if ov.get("DebtToEquityRatio") else None,
                "current_ratio": current_ratio,
                # Dividends
                "dividend_yield": _pct(ov, "DividendYield"),
                "payout_ratio": _pct(ov, "PayoutRatio"),
                # Analyst
                "target_mean_price": _safe_float_or_none(ov, "AnalystTargetPrice"),
                "target_high_price": None,  # Not in AV OVERVIEW
                "target_low_price": None,
                "recommendation": None,  # Not in AV OVERVIEW
                "num_analysts": _safe_int_or_none(ov, "NumberOfAnalystOpinions") if ov.get("NumberOfAnalystOpinions") else None,
            }
        except Exception as e:
            logger.error("Failed to get fundamentals for %s: %s", ticker, e)
            return {"ticker": ticker, "error": str(e)}

    def get_info(self, ticker: str) -> dict[str, Any]:
        """Return a yfinance-compatible info dict using Alpha Vantage data.

        Maps AV OVERVIEW fields to the yfinance key names so downstream
        tools (peer comparison, etc.) work without changes.
        """
        ov = self._get_overview(ticker)
        return {
            "longName": ov.get("Name", ticker),
            "shortName": ov.get("Name", ticker),
            "sector": ov.get("Sector", "Unknown"),
            "industry": ov.get("Industry", "Unknown"),
            "marketCap": _safe_float(ov, "MarketCapitalization"),
            "trailingPE": _safe_float_or_none(ov, "TrailingPE"),
            "forwardPE": _safe_float_or_none(ov, "ForwardPE"),
            "pegRatio": _safe_float_or_none(ov, "PEGRatio"),
            "priceToBook": _safe_float_or_none(ov, "BookValue"),
            "enterpriseToEbitda": _safe_float_or_none(ov, "EVToEBITDA"),
            "profitMargins": _safe_float_or_none(ov, "ProfitMargin"),
            "revenueGrowth": _safe_float_or_none(ov, "QuarterlyRevenueGrowthYOY"),
            "returnOnEquity": _safe_float_or_none(ov, "ReturnOnEquityTTM"),
            "dividendYield": _safe_float_or_none(ov, "DividendYield"),
            "debtToEquity": _safe_float_or_none(ov, "DebtToEquityRatio") if ov.get("DebtToEquityRatio") else None,
            "recommendationKey": None,  # Not available via AV
            "beta": _safe_float_or_none(ov, "Beta"),
            "sharesOutstanding": _safe_float_or_none(ov, "SharesOutstanding"),
            "averageVolume": None,  # Would need separate TIME_SERIES call
            "shortPercentOfFloat": None,  # Not in OVERVIEW
            "description": ov.get("Description", ""),
            "country": ov.get("Country", "Unknown"),
            "exchange": ov.get("Exchange", "Unknown"),
            "currency": ov.get("Currency", "USD"),
        }

    def get_insider_transactions(self, ticker: str) -> Any:
        """Alpha Vantage does not provide insider transaction data."""
        logger.info("Insider transactions not available via Alpha Vantage for %s", ticker)
        return None

    def get_earnings_history(self, ticker: str) -> Any:
        """Return earnings history from Alpha Vantage EARNINGS endpoint.

        Returns a pandas DataFrame with columns matching yfinance's
        earnings_history format: date, epsEstimate, epsActual, surprise,
        surprisePercent.
        """
        try:
            data = self._api_call({"function": "EARNINGS", "symbol": ticker})
            quarterly = data.get("quarterlyEarnings", [])
            if not quarterly:
                return None

            rows = []
            for q in quarterly:
                reported = q.get("reportedDate", "")
                est = q.get("estimatedEPS")
                actual = q.get("reportedEPS")
                surprise = q.get("surprise")
                surprise_pct = q.get("surprisePercentage")

                rows.append({
                    "Earnings Date": reported,
                    "EPS Estimate": float(est) if est and est != "None" else None,
                    "Reported EPS": float(actual) if actual and actual != "None" else None,
                    "Surprise(%)": float(surprise_pct) if surprise_pct and surprise_pct != "None" else None,
                })

            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            logger.error("Failed to get earnings history for %s: %s", ticker, e)
            return None

    def get_quarterly_earnings(self, ticker: str) -> Any:
        """Return quarterly earnings (revenue + earnings) as fallback.

        Uses the EARNINGS endpoint's quarterly data.
        """
        try:
            data = self._api_call({"function": "EARNINGS", "symbol": ticker})
            quarterly = data.get("quarterlyEarnings", [])
            if not quarterly:
                return None

            rows = []
            for q in quarterly:
                rows.append({
                    "Quarter": q.get("fiscalDateEnding", ""),
                    "Earnings": float(q["reportedEPS"]) if q.get("reportedEPS") and q["reportedEPS"] != "None" else None,
                })

            return pd.DataFrame(rows) if rows else None
        except Exception as e:
            logger.error("Failed to get quarterly earnings for %s: %s", ticker, e)
            return None

    def get_history(self, ticker: str, period: str = "6mo") -> Any:
        """Return historical price DataFrame (pandas) from Alpha Vantage.

        Columns: Open, High, Low, Close, Volume (matching yfinance format).
        """
        try:
            data = self._api_call({
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": "full",
                "datatype": "json",
            })

            ts_key = "Time Series (Daily)"
            if ts_key not in data:
                return pd.DataFrame()

            days = _period_to_days(period)
            cutoff = date.today() - timedelta(days=days)

            rows = []
            for date_str, bar in data[ts_key].items():
                bar_date = date.fromisoformat(date_str)
                if bar_date < cutoff:
                    continue
                rows.append({
                    "Date": bar_date,
                    "Open": float(bar["1. open"]),
                    "High": float(bar["2. high"]),
                    "Low": float(bar["3. low"]),
                    "Close": float(bar["5. adjusted close"]),
                    "Volume": int(float(bar["6. volume"])),
                })

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df = df.sort_values("Date").set_index("Date")
            return df
        except Exception as e:
            logger.error("Failed to get history for %s: %s", ticker, e)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Financial statement helpers
    # ------------------------------------------------------------------

    def _get_income_statement(self, ticker: str) -> list[dict[str, Any]]:
        """Fetch annual income statements (most recent first)."""
        try:
            data = self._api_call({
                "function": "INCOME_STATEMENT",
                "symbol": ticker,
            })
            return data.get("annualReports", [])
        except Exception:
            logger.warning("AV income statement failed for %s", ticker)
            return []

    def _get_balance_sheet(self, ticker: str) -> list[dict[str, Any]]:
        """Fetch annual balance sheets (most recent first)."""
        try:
            data = self._api_call({
                "function": "BALANCE_SHEET",
                "symbol": ticker,
            })
            return data.get("annualReports", [])
        except Exception:
            logger.warning("AV balance sheet failed for %s", ticker)
            return []


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


def _safe_float_or_none(data: dict, key: str) -> float | None:
    """Extract float or return None (for optional fields)."""
    val = data.get(key)
    if val is None or val == "None" or val == "-" or val == "" or val == "0":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(data: dict, key: str, default: int = 0) -> int:
    """Safely extract an int from an AV response dict."""
    val = data.get(key)
    if val is None or val == "None" or val == "-" or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_int_or_none(data: dict, key: str) -> int | None:
    """Extract int or return None."""
    val = data.get(key)
    if val is None or val == "None" or val == "-" or val == "":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _pct(data: dict, key: str) -> str | None:
    """Convert AV decimal value to percentage string."""
    val = _safe_float_or_none(data, key)
    if val is None:
        return None
    # AV OVERVIEW returns decimals (e.g., 0.25 for 25%)
    return f"{val * 100:.1f}%"


def _format_large_number(n: int | float | None) -> str | None:
    """Format large numbers into readable strings (e.g., 1.5T, 230B, 45M)."""
    if n is None or n == 0:
        return None
    n = float(n)
    if abs(n) >= 1e12:
        return f"${n / 1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"${n / 1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n / 1e6:.1f}M"
    return f"${n:,.0f}"


def _period_to_days(period: str) -> int:
    """Convert yfinance period string to approximate number of calendar days."""
    mapping = {
        "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365,
        "2y": 730, "5y": 1825, "10y": 3650, "ytd": 180, "max": 3650,
    }
    return mapping.get(period, 180)
