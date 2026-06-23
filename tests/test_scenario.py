"""
Tests that replicate the exact example scenario from the problem statement.

Scenario timeline
-----------------
T=0ms      Customer "stripe-test" makes first request → bucket full (100 tokens)
T=0ms      60 requests arrive → 60 allowed, bucket = 40
T=2000ms   Refill: 40 + (2 × 10) = 60 tokens
T=2000ms   70 requests arrive → 60 allowed, 10 denied, bucket = 0
T=7000ms   Refill: 0 + (5 × 10) = 50 tokens
T=7000ms   30 requests arrive → all 30 allowed, bucket = 20
T=17000ms  Refill: 20 + (10 × 10) = 120 → capped at 100
T=17000ms  80 requests arrive → all 80 allowed, bucket = 20
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.main import TokenBucketRateLimiter

CUSTOMER = "stripe-test"
CAPACITY = 100
REFILL_RATE = 10.0  # tokens per second


@pytest.fixture
def limiter():
    return TokenBucketRateLimiter(capacity=CAPACITY, refill_rate=REFILL_RATE)


# ── Helper ────────────────────────────────────────────────────────────────────

def fire_requests(limiter, customer_id, count, time_ms):
    """Fire *count* requests at *time_ms* and return (allowed, denied) counts."""
    allowed = denied = 0
    for _ in range(count):
        d = limiter.check(customer_id, time_ms)
        if d.allowed:
            allowed += 1
        else:
            denied += 1
    return allowed, denied


# ── T=0ms: initialisation ─────────────────────────────────────────────────────

def test_first_request_uses_full_bucket(limiter):
    """First-ever request should find a full bucket (capacity=100)."""
    d = limiter.check(CUSTOMER, current_time_ms=0)
    assert d.allowed is True
    assert d.remaining == 99   # 100 − 1


def test_t0_sixty_requests(limiter):
    """At T=0ms, 60 requests → 60 allowed, bucket left = 40."""
    allowed, denied = fire_requests(limiter, CUSTOMER, 60, time_ms=0)

    assert allowed == 60
    assert denied == 0
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 40


# ── T=2000ms: refill then 70 requests ────────────────────────────────────────

def test_t2000_refill_applied(limiter):
    """After 60 reqs at T=0, bucket at T=2000 should be 60 before consuming."""
    fire_requests(limiter, CUSTOMER, 60, time_ms=0)

    # Trigger a refill by making one request — check bucket before consumption.
    # We peek via a check and inspect remaining.
    d = limiter.check(CUSTOMER, current_time_ms=2_000)
    # bucket was 40, refill adds 20 → 60, consume 1 → 59
    assert d.allowed is True
    assert d.remaining == 59


def test_t2000_seventy_requests(limiter):
    """60 reqs at T=0, then 70 reqs at T=2000 → 60 allowed, 10 denied."""
    fire_requests(limiter, CUSTOMER, 60, time_ms=0)
    allowed, denied = fire_requests(limiter, CUSTOMER, 70, time_ms=2_000)

    assert allowed == 60
    assert denied == 10
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 0


# ── T=7000ms: refill then 30 requests ────────────────────────────────────────

def test_t7000_refill_and_thirty_requests(limiter):
    """After bucket hits 0 at T=2000, 5-second refill gives 50 tokens → all 30 served."""
    fire_requests(limiter, CUSTOMER, 60, time_ms=0)
    fire_requests(limiter, CUSTOMER, 70, time_ms=2_000)

    allowed, denied = fire_requests(limiter, CUSTOMER, 30, time_ms=7_000)

    assert allowed == 30
    assert denied == 0
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 20


# ── T=17000ms: cap enforcement ───────────────────────────────────────────────

def test_t17000_capacity_cap(limiter):
    """
    Bucket at 20 tokens + 10-second refill (100 tokens) should be capped at 100,
    not 120.  All 80 requests served, 20 remain.
    """
    fire_requests(limiter, CUSTOMER, 60, time_ms=0)
    fire_requests(limiter, CUSTOMER, 70, time_ms=2_000)
    fire_requests(limiter, CUSTOMER, 30, time_ms=7_000)

    allowed, denied = fire_requests(limiter, CUSTOMER, 80, time_ms=17_000)

    assert allowed == 80
    assert denied == 0
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 20


def test_t17000_bucket_never_exceeds_capacity(limiter):
    """The bucket must never exceed capacity, even after a long idle window."""
    # One request to initialise.
    limiter.check(CUSTOMER, current_time_ms=0)
    # Advance by 1 000 seconds — would add 10 000 tokens without capping.
    d = limiter.check(CUSTOMER, current_time_ms=1_000_000)
    assert d.remaining <= CAPACITY - 1