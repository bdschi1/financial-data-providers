"""Shared retry decorator for transient network/socket failures.

Yahoo and AlphaVantage providers already have their own tenacity decorators
scoped to their specific call sites. This module provides a generic
`network_retry` for socket-based providers (Bloomberg, IB) where transient
connection issues, session restarts, and service availability gaps can cause
short-lived failures that succeed on retry.

Pattern: exponential backoff 2s -> 4s -> 8s, 3 attempts, re-raise on final
failure. Matches the yahoo.py _yf_retry configuration for consistency.
"""

from __future__ import annotations

import logging

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

network_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((ConnectionError, OSError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
