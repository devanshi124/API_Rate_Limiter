"""
Demo — walks through the exact example scenario from the problem statement
and prints a clear, step-by-step trace.

Run from the project root:
    python demo/simulate.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import TokenBucketRateLimiter

# ── Config ────────────────────────────────────────────────────────────────────
CAPACITY    = 100
REFILL_RATE = 10.0   # tokens per second
CUSTOMER    = "stripe-test"

# ── Helpers ───────────────────────────────────────────────────────────────────

SEP = "─" * 60

def header(text: str) -> None:
    print(f"\n{SEP}")
    print(f"  {text}")
    print(SEP)

def fire_batch(limiter, customer, count, time_ms):
    """
    Send *count* requests at *time_ms* and return (allowed, denied).
    Also prints each denied request's retry_after_ms.
    """
    allowed = denied = 0
    first_retry_ms = None

    for i in range(count):
        d = limiter.check(customer, time_ms)
        if d.allowed:
            allowed += 1
        else:
            denied += 1
            if first_retry_ms is None:
                first_retry_ms = d.retry_after_ms

    return allowed, denied, first_retry_ms


def bucket_snapshot(limiter, customer, time_ms, label="Bucket after"):
    tokens = limiter.get_bucket_tokens(customer)
    print(f"  {label}: {tokens:.1f} tokens  (time={time_ms} ms)")

# ── Scenario ──────────────────────────────────────────────────────────────────

def run_scenario():
    limiter = TokenBucketRateLimiter(capacity=CAPACITY, refill_rate=REFILL_RATE)

    # ── T=0ms: initialise + 60 requests ──────────────────────────────────────
    header("T=0 ms  — Bucket initialised, 60 requests")
    print(f"  Customer '{CUSTOMER}' makes first contact.")
    print(f"  Expected initial bucket: {CAPACITY} tokens (full).")

    allowed, denied, retry = fire_batch(limiter, CUSTOMER, 60, time_ms=0)
    print(f"  Requests: 60  →  allowed={allowed}  denied={denied}")
    bucket_snapshot(limiter, CUSTOMER, 0)
    assert allowed == 60 and denied == 0, "FAILED: expected all 60 allowed"
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 40, "FAILED: expected 40"
    print("  ✓ Matches expected: bucket = 40")

    # ── T=2000ms: refill + 70 requests ───────────────────────────────────────
    header("T=2000 ms — Refill: 40 + (2 × 10) = 60,  70 requests arrive")
    print("  Refill window: 2 s × 10 tok/s = +20 tokens → 40 + 20 = 60")

    allowed, denied, retry = fire_batch(limiter, CUSTOMER, 70, time_ms=2_000)
    print(f"  Requests: 70  →  allowed={allowed}  denied={denied}")
    if retry is not None:
        print(f"  First denied request: retry_after_ms={retry} ms")
    bucket_snapshot(limiter, CUSTOMER, 2_000)
    assert allowed == 60 and denied == 10, "FAILED: expected 60/10 split"
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 0, "FAILED: expected 0"
    print("  ✓ Matches expected: 60 served, 10 denied, bucket = 0")

    # ── T=7000ms: refill + 30 requests ───────────────────────────────────────
    header("T=7000 ms — Refill: 0 + (5 × 10) = 50,  30 requests arrive")
    print("  Refill window: 5 s × 10 tok/s = +50 tokens → 0 + 50 = 50")

    allowed, denied, _ = fire_batch(limiter, CUSTOMER, 30, time_ms=7_000)
    print(f"  Requests: 30  →  allowed={allowed}  denied={denied}")
    bucket_snapshot(limiter, CUSTOMER, 7_000)
    assert allowed == 30 and denied == 0, "FAILED: expected all 30 allowed"
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 20, "FAILED: expected 20"
    print("  ✓ Matches expected: all 30 served, bucket = 20")

    # ── T=17000ms: refill with cap + 80 requests ─────────────────────────────
    header("T=17000 ms — Refill: 20 + (10 × 10) = 120 → capped at 100,  80 requests")
    print("  Refill window: 10 s × 10 tok/s = +100 tokens → 20 + 100 = 120")
    print(f"  Cap applied → bucket = {CAPACITY}")

    allowed, denied, _ = fire_batch(limiter, CUSTOMER, 80, time_ms=17_000)
    print(f"  Requests: 80  →  allowed={allowed}  denied={denied}")
    bucket_snapshot(limiter, CUSTOMER, 17_000)
    assert allowed == 80 and denied == 0, "FAILED: expected all 80 allowed"
    assert int(limiter.get_bucket_tokens(CUSTOMER)) == 20, "FAILED: expected 20"
    print("  ✓ Matches expected: all 80 served, bucket = 20")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  All scenario steps passed ✓")
    print(SEP)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  Token Bucket Rate Limiter — Demo")
    print("═" * 60)
    run_scenario()
    demo_bug_fixes()
    print()