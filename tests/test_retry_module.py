"""Tests for the shared network_retry decorator (_retry.py)."""

from __future__ import annotations

from bds_data_providers._retry import network_retry


def test_succeeds_first_try():
    calls: list[int] = []

    @network_retry
    def f() -> int:
        calls.append(1)
        return 42

    assert f() == 42
    assert len(calls) == 1


def test_retries_on_connection_error(monkeypatch):
    # Skip real exponential backoff so the test runs fast.
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_a, **_k: None)

    calls: list[int] = []

    @network_retry
    def flaky() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise ConnectionError("transient")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 2


def test_does_not_retry_on_value_error(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_a, **_k: None)

    calls: list[int] = []

    @network_retry
    def bad_input() -> None:
        calls.append(1)
        raise ValueError("unretryable")

    try:
        bad_input()
    except ValueError:
        pass

    assert len(calls) == 1


def test_gives_up_after_3_attempts(monkeypatch):
    import tenacity

    monkeypatch.setattr(tenacity.nap, "sleep", lambda *_a, **_k: None)

    calls: list[int] = []

    @network_retry
    def always_fails() -> None:
        calls.append(1)
        raise ConnectionError("always")

    try:
        always_fails()
    except ConnectionError:
        pass

    assert len(calls) == 3
