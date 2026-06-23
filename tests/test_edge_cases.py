"""
Edge-case tests for the Token Bucket Rate Limiter.

Covers
------
* Denial: retry_after_ms in milliseconds, not seconds
* No token consumed on denial
* Per-customer isolation (multiple tenants)
* Fractional refills (sub-second elapsed time)
* Exact boundary: bucket at exactly 1.0 token
* Clock monotonicity / backward clock guard
* Constructor validation
* Rapid burst up to capacity, then hard stop
* Long idle fully replenishes (capped at capacity)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import pytest
from src.main import TokenBucketRateLimiter


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def limiter():
    """Standard 100-token bucket, 10 tokens/s."""
    return TokenBucketRateLimiter(capacity=100, refill_rate=10.0)


@pytest.fixture
def small_limiter():
    """Tiny bucket (5 tokens, 2 tokens/s) for tighter arithmetic."""
    return TokenBucketRateLimiter(capacity=5, refill_rate=2.0)


# ── BUG-1: initial bucket is full ────────────────────────────────────────────

def test_new_customer_starts_at_capacity(limiter):
    d = limiter.check("new-customer", current_time_ms=0)
    assert d.allowed is True
    assert d.remaining == 99  # capacity(100) − 1


def test_new_customer_can_burst_to_capacity(limiter):
    """All 100 initial tokens should be usable in one burst."""
    results = [limiter.check("burst-customer", 0) for _ in range(100)]
    assert all(r.allowed for r in results)
    assert results[-1].remaining == 0


def test_101st_request_denied(limiter):
    for _ in range(100):
        limiter.check("burst-customer", 0)
    d = limiter.check("burst-customer", 0)
    assert d.allowed is False
    assert d.remaining == 0


# ── BUG-2: capacity cap ───────────────────────────────────────────────────────

def test_tokens_never_exceed_capacity_after_refill(limiter):
    limiter.check("cap-test", 0)        # initialise
    # 10 000 seconds would add 100 000 tokens without capping
    d = limiter.check("cap-test", 10_000_000)
    assert d.remaining <= 99            # capacity - 1 consumed


def test_tokens_capped_at_capacity_exact(small_limiter):
    """Bucket of 5, spend 5, wait long enough to refill 10 — must cap at 5."""
    for _ in range(5):
        small_limiter.check("capped", 0)
    # 5 s × 2 tok/s = 10 tokens earned → capped to 5
    d = small_limiter.check("capped", 5_000)
    assert d.remaining == 4            # 5 − 1


# ── BUG-3: retry_after_ms in milliseconds ────────────────────────────────────

def test_retry_after_ms_is_milliseconds_not_seconds(limiter):
    """
    With refill_rate=10 tok/s and an empty bucket, the client needs 1 token.
    That takes 1/10 s = 100 ms — NOT 0 (the buggy int-cast of 0.1 seconds).
    """
    for _ in range(100):
        limiter.check("retry-ms-test", 0)
    d = limiter.check("retry-ms-test", 0)
    assert d.allowed is False
    assert d.retry_after_ms == 100    # ceil(0.1 * 1000)


def test_retry_after_ms_various_rates():
    """retry_after_ms should correctly reflect different refill rates."""
    # 1 token per second → need 1 token → 1000 ms
    rl = TokenBucketRateLimiter(capacity=1, refill_rate=1.0)
    limiter_check = rl.check("c", 0)    # uses the 1 token
    assert limiter_check.allowed
    d = rl.check("c", 0)
    assert d.retry_after_ms == 1_000   # 1 token at 1 tok/s = 1 s = 1000 ms

    # 4 tokens per second → 250 ms
    rl2 = TokenBucketRateLimiter(capacity=1, refill_rate=4.0)
    rl2.check("c2", 0)
    d2 = rl2.check("c2", 0)
    assert d2.retry_after_ms == 250


def test_retry_after_ms_zero_when_allowed(limiter):
    d = limiter.check("zero-retry", 0)
    assert d.allowed is True
    assert d.retry_after_ms == 0


# ── Token not consumed on denial ─────────────────────────────────────────────

def test_denied_request_does_not_consume_token(limiter):
    """Bucket must stay at 0 (not go negative) after a denied request."""
    for _ in range(100):
        limiter.check("no-consume", 0)

    before = limiter.get_bucket_tokens("no-consume")
    d = limiter.check("no-consume", 0)
    after = limiter.get_bucket_tokens("no-consume")

    assert d.allowed is False
    assert before == pytest.approx(0.0, abs=1e-9)
    assert after == pytest.approx(0.0, abs=1e-9)


# ── Per-customer isolation ────────────────────────────────────────────────────

def test_customers_are_isolated(limiter):
    """Draining customer A must not affect customer B."""
    for _ in range(100):
        limiter.check("customer-A", 0)

    # Customer B should still have a full bucket
    d = limiter.check("customer-B", 0)
    assert d.allowed is True
    assert d.remaining == 99


def test_many_customers_independent(limiter):
    customers = [f"tenant-{i}" for i in range(50)]
    for c in customers:
        d = limiter.check(c, 0)
        assert d.allowed is True, f"{c} should be allowed on first request"


# ── Fractional / partial refill ───────────────────────────────────────────────

def test_partial_refill_sub_second(small_limiter):
    """500 ms at 2 tok/s should add exactly 1 token."""
    for _ in range(5):
        small_limiter.check("partial", 0)          # drain to 0
    d = small_limiter.check("partial", 500)        # +1 token, consume it
    assert d.allowed is True
    assert d.remaining == 0


def test_fractional_tokens_accumulate():
    """
    Very slow refill: 0.5 tok/s.
    After 1 500 ms the bucket should have 0.75 tokens (< 1) → denied.
    After 2 000 ms the bucket should have 1.0 token → allowed.
    """
    rl = TokenBucketRateLimiter(capacity=5, refill_rate=0.5)
    for _ in range(5):
        rl.check("slow", 0)

    d1 = rl.check("slow", 1_500)    # 0.75 tokens → denied
    assert d1.allowed is False

    d2 = rl.check("slow", 2_000)    # 0.75 + 0.25 = 1.0 token → allowed
    assert d2.allowed is True


# ── Boundary: exactly 1.0 token ──────────────────────────────────────────────

def test_exactly_one_token_is_allowed(small_limiter):
    """Bucket with precisely 1.0 token should allow the request."""
    for _ in range(5):
        small_limiter.check("exact-one", 0)        # drain to 0
    # 2 tok/s × 0.5 s = 1.0 token exactly
    d = small_limiter.check("exact-one", 500)
    assert d.allowed is True
    assert d.remaining == 0


# ── Clock / time edge cases ───────────────────────────────────────────────────

def test_same_timestamp_no_refill(limiter):
    """Two calls at the same timestamp should not double-refill."""
    limiter.check("same-ts", 0)
    tokens_after_first = limiter.get_bucket_tokens("same-ts")
    limiter.check("same-ts", 0)
    tokens_after_second = limiter.get_bucket_tokens("same-ts")
    # No time has passed → no tokens added; second call just consumes one more
    assert tokens_after_second == pytest.approx(tokens_after_first - 1, abs=1e-9)


def test_backward_clock_does_not_crash(limiter):
    """A clock going backwards should not raise an exception or add tokens."""
    limiter.check("back-clock", 5_000)
    tokens_at_5s = limiter.get_bucket_tokens("back-clock")
    # Call with an earlier timestamp (clock went backward)
    d = limiter.check("back-clock", 1_000)
    tokens_after = limiter.get_bucket_tokens("back-clock")
    # Should succeed (consume a token) and not add tokens
    if d.allowed:
        assert tokens_after <= tokens_at_5s


# ── Constructor validation ────────────────────────────────────────────────────

def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=0, refill_rate=10.0)


def test_invalid_refill_rate_raises():
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=100, refill_rate=0.0)


def test_negative_capacity_raises():
    with pytest.raises(ValueError):
        TokenBucketRateLimiter(capacity=-5, refill_rate=10.0)


# ── Long idle fully replenishes ───────────────────────────────────────────────

def test_long_idle_replenishes_to_capacity(limiter):
    """
    Drain the bucket completely, then idle for much longer than needed to
    refill — the bucket must be full (capped at capacity).
    """
    for _ in range(100):
        limiter.check("idle-test", 0)
    # 100 tokens needed at 10/s = 10 s → wait 1000 s to be safe
    d = limiter.check("idle-test", 1_000_000)
    assert d.allowed is True
    assert d.remaining == 99   # 100 − 1