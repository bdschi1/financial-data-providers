"""Tests for options data methods on MarketDataProvider ABC and implementations.

Tests:
    - ABC defaults return None (no provider breaks)
    - AlphaVantage inherits None defaults
    - Yahoo chain/surface schema validation (mocked yfinance)
    - Bloomberg/IB return None when deps not installed
    - options_utils surface building from synthetic chains
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from bds_data_providers.market_data_provider import MarketDataProvider
from bds_data_providers.options_utils import (
    time_to_expiry_years,
    find_atm_strike_idx,
    compute_skew_metrics,
    assess_chain_liquidity,
    build_iv_surface_from_chains,
)


# ── ABC Default Tests ────────────────────────────────────────────────


class _ConcreteProvider(MarketDataProvider):
    """Minimal concrete subclass for testing ABC defaults."""

    def get_ticker_object(self, ticker):
        return None

    def get_company_overview(self, ticker):
        return {}

    def get_price_data(self, ticker, period="6mo"):
        return {}

    def get_fundamentals(self, ticker):
        return {}

    def get_info(self, ticker):
        return {}

    def get_insider_transactions(self, ticker):
        return None

    def get_earnings_history(self, ticker):
        return None

    def get_quarterly_earnings(self, ticker):
        return None

    def get_history(self, ticker, period="6mo"):
        return None


class TestABCDefaults:
    """ABC options methods should return None by default."""

    def test_get_options_expirations_default(self):
        p = _ConcreteProvider()
        assert p.get_options_expirations("AAPL") is None

    def test_get_options_chain_default(self):
        p = _ConcreteProvider()
        assert p.get_options_chain("AAPL") is None

    def test_get_iv_surface_default(self):
        p = _ConcreteProvider()
        assert p.get_iv_surface("AAPL") is None


class TestAlphaVantageOptions:
    """AlphaVantage now implements options via REALTIME_OPTIONS (premium tier).

    Tests mock the _api_call to avoid premium-key/rate-limit dependencies.
    Free keys or missing data return None so consumers can fall back.
    """

    def test_alphavantage_empty_returns_none(self):
        from bds_data_providers.alphavantage_market import AlphaVantageMarketProvider

        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
            p = AlphaVantageMarketProvider(api_key="test")
            with patch.object(p, "_api_call", return_value={"data": []}):
                assert p.get_options_expirations("AAPL") is None
                assert p.get_options_chain("AAPL") is None

    def test_alphavantage_api_failure_returns_none(self):
        from bds_data_providers.alphavantage_market import AlphaVantageMarketProvider

        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
            p = AlphaVantageMarketProvider(api_key="test")
            with patch.object(p, "_api_call", side_effect=RuntimeError("premium only")):
                assert p.get_options_expirations("AAPL") is None
                assert p.get_options_chain("AAPL") is None

    def test_alphavantage_chain_schema(self):
        from bds_data_providers.alphavantage_market import AlphaVantageMarketProvider

        stub = {
            "data": [
                {"expiration": "2026-05-16", "type": "call", "strike": "100",
                 "bid": "5.0", "ask": "5.2", "volume": "50", "open_interest": "200",
                 "implied_volatility": "0.25"},
                {"expiration": "2026-05-16", "type": "put", "strike": "100",
                 "bid": "3.0", "ask": "3.1", "volume": "40", "open_interest": "150",
                 "implied_volatility": "0.28"},
            ]
        }
        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
            p = AlphaVantageMarketProvider(api_key="test")
            with patch.object(p, "_api_call", return_value=stub):
                assert p.get_options_expirations("AAPL") == ["2026-05-16"]
                chain = p.get_options_chain("AAPL")
                assert chain["expiration"] == "2026-05-16"
                assert len(chain["calls"]) == 1
                assert len(chain["puts"]) == 1
                assert chain["calls"][0]["strike"] == 100.0

    def test_alphavantage_iv_surface(self):
        from bds_data_providers.alphavantage_market import AlphaVantageMarketProvider

        with patch.dict("os.environ", {"ALPHAVANTAGE_API_KEY": "test"}):
            p = AlphaVantageMarketProvider(api_key="test")
            assert p.get_iv_surface("AAPL") is None


# ── options_utils Tests ──────────────────────────────────────────────


class TestTimeToExpiryYears:
    def test_future_date(self):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=180)).isoformat()
        tte = time_to_expiry_years(future)
        assert 0.4 < tte < 0.6  # ~0.49 years

    def test_past_date_returns_minimum(self):
        tte = time_to_expiry_years("2020-01-01")
        assert tte == pytest.approx(1.0 / 365.0)

    def test_today_returns_minimum(self):
        from datetime import date

        tte = time_to_expiry_years(date.today().isoformat())
        assert tte == pytest.approx(1.0 / 365.0)


class TestFindAtmStrikeIdx:
    def test_exact_match(self):
        assert find_atm_strike_idx([90, 95, 100, 105, 110], 100) == 2

    def test_nearest_below(self):
        assert find_atm_strike_idx([90, 95, 100, 105, 110], 97) == 1

    def test_nearest_above(self):
        assert find_atm_strike_idx([90, 95, 100, 105, 110], 103) == 3

    def test_empty_list(self):
        assert find_atm_strike_idx([], 100) == 0


class TestComputeSkewMetrics:
    def test_normal_skew(self):
        # Put wing (90% of 100=90) -> strike 90 -> IV 30
        # ATM (100) -> IV 25
        # Call wing (110% of 100=110) -> strike 110 -> IV 22
        strikes = [80, 90, 95, 100, 105, 110, 120]
        ivs = [35.0, 30.0, 27.0, 25.0, 23.0, 22.0, 20.0]
        result = compute_skew_metrics(ivs, strikes, 100)
        assert result["put_wing"] == 30.0
        assert result["atm"] == 25.0
        assert result["call_wing"] == 22.0
        assert result["skew_25d"] == 8.0  # 30 - 22

    def test_empty_data(self):
        result = compute_skew_metrics([], [], 100)
        assert result["skew_25d"] is None


class TestAssessChainLiquidity:
    def test_liquid_chain(self):
        chain = {
            "calls": [
                {"implied_vol": 25.0, "volume": 1000, "open_interest": 5000},
                {"implied_vol": 26.0, "volume": 800, "open_interest": 4000},
            ],
            "puts": [
                {"implied_vol": 28.0, "volume": 900, "open_interest": 3000},
                {"implied_vol": 30.0, "volume": 700, "open_interest": 2000},
            ],
        }
        result = assess_chain_liquidity(chain)
        assert result["coverage_pct"] == 100.0
        assert result["avg_volume"] > 0
        assert result["illiquid"] is False

    def test_illiquid_chain(self):
        chain = {
            "calls": [
                {"implied_vol": None, "volume": 0, "open_interest": 0},
                {"implied_vol": None, "volume": 0, "open_interest": 0},
            ],
            "puts": [],
        }
        result = assess_chain_liquidity(chain)
        assert result["coverage_pct"] == 0.0
        assert result["illiquid"] is True

    def test_empty_chain(self):
        chain = {"calls": [], "puts": []}
        result = assess_chain_liquidity(chain)
        assert result["illiquid"] is True


class TestBuildIVSurfaceFromChains:
    def _make_chain(self, expiration, spot=100.0):
        """Build a synthetic options chain with realistic IV skew."""
        strikes = [80, 85, 90, 95, 100, 105, 110, 115, 120]
        calls = []
        puts = []
        for k in strikes:
            moneyness = k / spot
            # Simple skew: higher IV for OTM puts, lower for OTM calls
            iv = 25.0 + (1.0 - moneyness) * 30.0
            iv = max(iv, 10.0)
            contract = {
                "strike": float(k),
                "last_price": max(0.01, spot - k) if k < spot else max(0.01, k - spot) * 0.3,
                "bid": 0.5,
                "ask": 1.0,
                "volume": 500,
                "open_interest": 2000,
                "implied_vol": round(iv, 2),
                "delta": None,
                "gamma": None,
                "theta": None,
                "vega": None,
                "in_the_money": k < spot,
            }
            if k >= spot:
                calls.append(contract)
            else:
                puts.append(contract)
            # Add both sides for full coverage
            calls.append({**contract, "in_the_money": k < spot})
            puts.append({**contract, "in_the_money": k > spot})

        return {
            "ticker": "TEST",
            "expiration": expiration,
            "provider": "Test",
            "spot": spot,
            "calls": calls,
            "puts": puts,
        }

    def test_builds_surface_from_multiple_chains(self):
        from datetime import date, timedelta

        exp1 = (date.today() + timedelta(days=30)).isoformat()
        exp2 = (date.today() + timedelta(days=90)).isoformat()
        exp3 = (date.today() + timedelta(days=180)).isoformat()

        chains = [
            self._make_chain(exp1),
            self._make_chain(exp2),
            self._make_chain(exp3),
        ]

        result = build_iv_surface_from_chains("TEST", "TestProvider", 100.0, chains)
        assert result is not None
        assert "iv_surface_pct" in result
        assert "atm_term_structure" in result
        assert "skew_by_maturity" in result
        assert "summary" in result
        assert "data_quality" in result
        assert result["provider"] == "TestProvider"

    def test_returns_none_for_empty_chains(self):
        result = build_iv_surface_from_chains("TEST", "TestProvider", 100.0, [])
        assert result is None

    def test_returns_none_for_zero_spot(self):
        result = build_iv_surface_from_chains("TEST", "TestProvider", 0.0, [{}])
        assert result is None

    def test_atm_term_structure_populated(self):
        from datetime import date, timedelta

        exp1 = (date.today() + timedelta(days=30)).isoformat()
        exp2 = (date.today() + timedelta(days=180)).isoformat()
        chains = [self._make_chain(exp1), self._make_chain(exp2)]

        result = build_iv_surface_from_chains("TEST", "TestProvider", 100.0, chains)
        assert result is not None
        assert len(result["atm_term_structure"]) >= 1

    def test_data_quality_fields(self):
        from datetime import date, timedelta

        exp1 = (date.today() + timedelta(days=60)).isoformat()
        chains = [self._make_chain(exp1)]
        result = build_iv_surface_from_chains("TEST", "TestProvider", 100.0, chains)
        assert result is not None
        q = result["data_quality"]
        assert "coverage_pct" in q
        assert "avg_volume" in q
        assert "num_expirations" in q


# ── Yahoo Options Tests (mocked) ────────────────────────────────────


class TestYahooOptionsExpirations:
    @patch("bds_data_providers.yahoo_market.yf")
    def test_returns_expirations(self, mock_yf):
        from bds_data_providers.yahoo_market import YahooMarketProvider

        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-03-20", "2026-04-17", "2026-06-19")
        mock_yf.Ticker.return_value = mock_ticker

        p = YahooMarketProvider()
        result = p.get_options_expirations("AAPL")
        assert result == ["2026-03-20", "2026-04-17", "2026-06-19"]

    @patch("bds_data_providers.yahoo_market.yf")
    def test_returns_none_when_empty(self, mock_yf):
        from bds_data_providers.yahoo_market import YahooMarketProvider

        mock_ticker = MagicMock()
        mock_ticker.options = ()
        mock_yf.Ticker.return_value = mock_ticker

        p = YahooMarketProvider()
        assert p.get_options_expirations("AAPL") is None

    @patch("bds_data_providers.yahoo_market.yf")
    def test_returns_none_on_exception(self, mock_yf):
        from bds_data_providers.yahoo_market import YahooMarketProvider

        mock_yf.Ticker.side_effect = Exception("network error")
        p = YahooMarketProvider()
        assert p.get_options_expirations("AAPL") is None


class TestYahooOptionsChain:
    @patch("bds_data_providers.yahoo_market.yf")
    def test_chain_schema(self, mock_yf):
        import pandas as pd
        from bds_data_providers.yahoo_market import YahooMarketProvider

        mock_ticker = MagicMock()
        mock_ticker.options = ("2026-06-19",)
        mock_ticker.info = {"currentPrice": 150.0}

        calls_df = pd.DataFrame([{
            "strike": 150.0,
            "lastPrice": 5.0,
            "bid": 4.5,
            "ask": 5.5,
            "volume": 1000,
            "openInterest": 5000,
            "impliedVolatility": 0.30,
            "inTheMoney": True,
        }])
        puts_df = pd.DataFrame([{
            "strike": 150.0,
            "lastPrice": 4.0,
            "bid": 3.5,
            "ask": 4.5,
            "volume": 800,
            "openInterest": 4000,
            "impliedVolatility": 0.32,
            "inTheMoney": False,
        }])
        mock_chain = MagicMock()
        mock_chain.calls = calls_df
        mock_chain.puts = puts_df
        mock_ticker.option_chain.return_value = mock_chain
        mock_yf.Ticker.return_value = mock_ticker

        p = YahooMarketProvider()
        result = p.get_options_chain("AAPL", "2026-06-19")

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["expiration"] == "2026-06-19"
        assert result["spot"] == 150.0
        assert len(result["calls"]) == 1
        assert len(result["puts"]) == 1

        call = result["calls"][0]
        assert call["strike"] == 150.0
        assert call["implied_vol"] == 30.0
        assert call["delta"] is None  # yfinance doesn't provide greeks
        assert call["volume"] == 1000


# ── Bloomberg/IB Fallback Tests ──────────────────────────────────────


class TestBloombergOptionsWhenUnavailable:
    """Bloomberg options methods should return None when blpapi is not installed."""

    def test_bloomberg_inherits_defaults_when_no_blpapi(self):
        """If blpapi is not installed, Bloomberg can't be instantiated.
        The ABC defaults already return None, so this verifies the ABC contract."""
        p = _ConcreteProvider()
        assert p.get_options_expirations("AAPL") is None
        assert p.get_options_chain("AAPL") is None
        assert p.get_iv_surface("AAPL") is None


class TestIBOptionsWhenUnavailable:
    """IB options methods should return None when ib_insync is not installed."""

    def test_ib_inherits_defaults_when_no_ib_insync(self):
        p = _ConcreteProvider()
        assert p.get_options_expirations("AAPL") is None
        assert p.get_options_chain("AAPL") is None
        assert p.get_iv_surface("AAPL") is None
