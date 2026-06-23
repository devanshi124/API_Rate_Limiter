"""
Token Bucket Rate Limiter — corrected and extended implementation.

Design notes
------------
* Lazy initialisation — a customer's bucket is created on first request.
* Thread safety — a threading.Lock guards each mutation so the limiter
  is safe to call from multiple concurrent workers/threads.
* Floating-point tokens — we track fractional tokens internally so short
  bursts that span a partial refill window work correctly.  The `remaining`
  field in Decision is always floored to an int (what the caller sees).
"""

import threading
from typing import Dict

from src.types import BucketState, Decision
from src.utils import clamp, compute_tokens_to_add, tokens_to_wait_ms


class TokenBucketRateLimiter:
    """
    Token-bucket rate limiter for a multi-tenant SaaS API.

    Parameters
    ----------
    capacity    : Maximum tokens a bucket can hold (burst ceiling).
    refill_rate : Tokens added per second (long-run average request rate).
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        if refill_rate <= 0:
            raise ValueError(f"refill_rate must be positive, got {refill_rate}")

        self.capacity: int = capacity
        self.refill_rate: float = refill_rate          # tokens / second

        self._buckets: Dict[str, BucketState] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, customer_id: str, current_time_ms: int) -> Decision:
        """
        Evaluate one API request for *customer_id* at *current_time_ms*.

        Steps
        -----
        1. Initialise the bucket on first contact (full, at capacity).
        2. Refill tokens proportional to elapsed time since last call.
        3. Cap at capacity  (BUG-2 fix).
        4. Consume one token if available  →  allowed=True.
        5. Otherwise compute retry_after_ms in **milliseconds** (BUG-3 fix).

        Parameters
        ----------
        customer_id     : Opaque string identifying the tenant.
        current_time_ms : Wall-clock time of the request in milliseconds.

        Returns
        -------
        Decision  with allowed, remaining, and retry_after_ms populated.
        """
        with self._lock:
            bucket = self._get_or_create_bucket(customer_id, current_time_ms)
            self._refill(bucket, current_time_ms)

            if bucket.tokens >= 1.0:
                # --- Allow ---
                bucket.tokens -= 1.0
                return Decision(
                    allowed=True,
                    remaining=int(bucket.tokens),   # floor to int for the caller
                    retry_after_ms=0,
                )
            else:
                # --- Deny ---
                tokens_needed = 1.0 - bucket.tokens
                wait_ms = tokens_to_wait_ms(tokens_needed, self.refill_rate)
                return Decision(
                    allowed=False,
                    remaining=0,
                    retry_after_ms=wait_ms,         # BUG-3 fix: ms, not seconds
                )

    def get_bucket_tokens(self, customer_id: str) -> float:
        """Return the current (un-refilled) token count for inspection/testing."""
        with self._lock:
            if customer_id not in self._buckets:
                return float(self.capacity)
            return self._buckets[customer_id].tokens

    def reset_customer(self, customer_id: str) -> None:
        """Remove a customer's bucket (e.g. for testing teardown)."""
        with self._lock:
            self._buckets.pop(customer_id, None)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_create_bucket(
        self, customer_id: str, current_time_ms: int
    ) -> BucketState:
        """
        Return the existing BucketState or create a new full one.

        BUG-1 fix: new buckets start at *capacity*, not 0.
        """
        if customer_id not in self._buckets:
            self._buckets[customer_id] = BucketState(
                tokens=float(self.capacity),   # ← BUG-1 fix
                last_refill_ms=current_time_ms,
            )
        return self._buckets[customer_id]

    def _refill(self, bucket: BucketState, current_time_ms: int) -> None:
        """
        Add tokens earned since the last request and update the timestamp.

        BUG-2 fix: clamp so tokens never exceed capacity.
        """
        elapsed_ms = current_time_ms - bucket.last_refill_ms
        if elapsed_ms < 0:
            # Clock went backwards — treat as zero elapsed time (defensive).
            elapsed_ms = 0

        tokens_earned = compute_tokens_to_add(elapsed_ms, self.refill_rate)
        bucket.tokens = clamp(
            bucket.tokens + tokens_earned,
            lo=0.0,
            hi=float(self.capacity),            # ← BUG-2 fix
        )
        bucket.last_refill_ms = current_time_ms