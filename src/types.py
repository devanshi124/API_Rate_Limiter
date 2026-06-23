from dataclasses import dataclass


@dataclass
class Decision:
    """
    Result returned by the rate limiter for every API request.

    Fields
    ------
    allowed        : True if the request is permitted.
    remaining      : Tokens left in the bucket after this request.
                     Always 0 when the request is denied.
    retry_after_ms : Milliseconds the caller should wait before retrying.
                     Always 0 when the request is allowed.
    """
    allowed: bool
    remaining: int
    retry_after_ms: int


@dataclass
class BucketState:
    """
    Internal snapshot of a single customer's token bucket.

    Fields
    ------
    tokens        : Current floating-point token count.
    last_refill_ms: Timestamp (ms) of the last time tokens were added.
    """
    tokens: float
    last_refill_ms: int