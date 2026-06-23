"""
Utility functions for the Token Bucket Rate Limiter.
"""


def compute_tokens_to_add(elapsed_ms: int, refill_rate: float) -> float:
    """
    Convert elapsed wall-clock time into a token count.

    Parameters
    ----------
    elapsed_ms   : Milliseconds since the last refill timestamp.
    refill_rate  : Tokens added per second (e.g. 10.0).

    Returns
    -------
    float  Number of tokens earned during the elapsed window.
    """
    return (elapsed_ms / 1_000.0) * refill_rate


def clamp(value: float, lo: float, hi: float) -> float:
    """
    Clamp *value* to the closed interval [lo, hi].

    Used to enforce the bucket capacity ceiling so accumulated tokens
    never exceed *hi* and never go below *lo* (defensive guard).
    """
    return max(lo, min(value, hi))


def tokens_to_wait_ms(tokens_needed: float, refill_rate: float) -> int:
    """
    Calculate how many **milliseconds** a client must wait before
    *tokens_needed* tokens will have been added at *refill_rate*.

    Parameters
    ----------
    tokens_needed : How many additional tokens are required (≥ 0).
    refill_rate   : Tokens per second.

    Returns
    -------
    int  Ceiling-rounded wait time in milliseconds.
         Returns 0 when tokens_needed ≤ 0 or refill_rate ≤ 0.

    Notes
    -----
    We use ceiling (math.ceil) so the client is never told to retry
    before the token is actually available — a wait of 99 ms for a
    1-token deficit at 10 tok/s would still leave the bucket at 0.99.
    """
    import math
    if refill_rate <= 0 or tokens_needed <= 0:
        return 0
    wait_seconds = tokens_needed / refill_rate
    return math.ceil(wait_seconds * 1_000)