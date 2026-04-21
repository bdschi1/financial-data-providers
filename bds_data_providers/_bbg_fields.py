"""Bloomberg field-name validation.

Bloomberg BDH/BDP/BDS queries silently return empty results when a field name
is misspelled or deprecated. That turns runtime data errors into quiet
downstream NaNs. This module validates field names against a whitelist of
commonly-used equity/reference fields before a query is issued, and raises
UnknownBloombergField early when something unexpected is requested.

The whitelist is deliberately non-exhaustive -- Bloomberg has >50,000 fields
across asset classes. The set below covers the fields used by this repo and
its consumers. Unknown fields can be added via `register_fields()` at runtime
rather than editing this file.
"""

from __future__ import annotations


class UnknownBloombergField(ValueError):
    """Raised when a Bloomberg field is not in the validated whitelist."""


_PRICE_FIELDS: frozenset[str] = frozenset({
    "PX_OPEN",
    "PX_HIGH",
    "PX_LOW",
    "PX_LAST",
    "PX_BID",
    "PX_ASK",
    "PX_MID",
    "BID",
    "ASK",
    "LAST_PRICE",
    "PX_VOLUME",
    "VOLUME",
    "EQY_WEIGHTED_AVG_PX",
    "VWAP",
    "PX_YEST_CLOSE",
})

_REF_FIELDS: frozenset[str] = frozenset({
    "NAME",
    "SHORT_NAME",
    "LONG_COMP_NAME",
    "SECURITY_NAME",
    "COUNTRY",
    "CRNCY",
    "GICS_SECTOR_NAME",
    "GICS_INDUSTRY_NAME",
    "GICS_SUB_INDUSTRY_NAME",
    "INDUSTRY_SECTOR",
    "INDUSTRY_GROUP",
    "INDUSTRY_SUBGROUP",
    "EXCHANGE",
    "PRIMARY_EXCHANGE_NAME",
    "CUR_MKT_CAP",
    "EQY_SH_OUT",
    "CHAIN_TICKERS",
})

_FUNDAMENTAL_FIELDS: frozenset[str] = frozenset({
    "PE_RATIO",
    "BEST_PE_RATIO",
    "PX_TO_BOOK_RATIO",
    "PX_TO_SALES_RATIO",
    "EV_TO_T12M_EBITDA",
    "DIVIDEND_YIELD",
    "EQY_DVD_YLD_IND",
    "TRAIL_12M_EPS",
    "IS_EPS",
    "BEST_EPS",
    "NET_INCOME",
    "SALES_REV_TURN",
    "EBITDA",
    "TOTAL_DEBT",
    "CASH_AND_ST_INVESTMENTS",
    "TOT_COMMON_EQY",
    "BOOK_VAL_PER_SH",
    "RETURN_ON_ASSET",
    "RETURN_COM_EQY",
    "OPER_MARGIN",
    "PROF_MARGIN",
})

_RATE_FIELDS: frozenset[str] = frozenset({
    "YLD_YTM_MID",
    "YLD_CNV_LAST",
    "YLD_YTM_LAST",
    "PX_LAST_YIELD",
})

_OPTIONS_FIELDS: frozenset[str] = frozenset({
    "OPT_STRIKE_PX",
    "OPT_EXPIRE_DT",
    "OPT_PUT_CALL",
    "OPT_IMPLIED_VOLATILITY_LAST",
    "IVOL_MID",
    "OPT_UNDL_TICKER",
    "CHAIN_TICKERS",
})

_KNOWN_FIELDS: set[str] = set().union(
    _PRICE_FIELDS,
    _REF_FIELDS,
    _FUNDAMENTAL_FIELDS,
    _RATE_FIELDS,
    _OPTIONS_FIELDS,
)


def register_fields(fields: list[str] | set[str]) -> None:
    """Add additional Bloomberg fields to the validator whitelist at runtime.

    Use this when a consumer needs a niche field not in the default set
    (e.g., fixed-income or commodity-specific fields). Preferred over
    suppressing validation entirely.
    """
    _KNOWN_FIELDS.update(fields)


def is_known_field(field: str) -> bool:
    """Return True if *field* is in the validated whitelist."""
    return field in _KNOWN_FIELDS


def validate_fields(fields: list[str]) -> None:
    """Validate a list of Bloomberg fields, raising on the first unknown.

    Args:
        fields: List of BBG field names (e.g., ["PX_LAST", "VOLUME"]).

    Raises:
        UnknownBloombergField: If any field is not in the whitelist. The
            error message lists the unknown fields.
    """
    unknown = [f for f in fields if f not in _KNOWN_FIELDS]
    if unknown:
        msg = (
            f"Unknown Bloomberg field(s): {unknown}. "
            f"Either fix the field name or call "
            f"bds_data_providers._bbg_fields.register_fields() to whitelist."
        )
        raise UnknownBloombergField(msg)


def known_fields() -> frozenset[str]:
    """Return an immutable snapshot of the current whitelist."""
    return frozenset(_KNOWN_FIELDS)
