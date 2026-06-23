NAME:-DEVANSHI THAKER
LANGUAGE:-PYTHON

1.Problem Understanding:-
Design a Rate Limiter where a customer uses API(having 100 tokens initially) , 1req=1token used, 10 tokens added every sec(stops when tokens reaches to 100),
If customer is out of tokens,calculate the time in ms remaining to add new tokens and send that time as the response.


2).Assumptions:
Each custtomer has their individual container of tokens.
If a request is denied, no consumption of the token.

3).Erros Found in Problem statement:-
    BUG 1).When a request is denied, retry_after_ms must equal the number of seconds the client needs to wait until the
bucket will have at least 1 token. (Note: the field name says "ms" — pay careful attention to the unit.) 

In this statement the return should be in ms not seconds.

BUG 2).3 Refill tokens continuously based on elapsed time since the last request — not on a fixed interval.

→ Suggested approach: Implement a background timer that fires every 1 second and adds refill_rate tokens to
each active customer's bucket. This separates refill logic from request handling. Cap so the bucket never exceeds
capacity.

Both this statements are contradicting, I chose the second approach.

4). Bugs Found in Starter Code
BUG1-The bucket starts empty rather than starting with 100 tokens.

BUG2- ON LINE 26- The capacity could exceed 100 after refill.

BUG3:-variable says seconds instead of ms.

5. My Solution Design:-
STEP-1).CREATE CUSTOMER and asiign them an individual container for token storage.
STEP-2).Fill the container to 100.
STEP-3).Intialize a timer adding 10 tokens every second and adds it but should not exceed the bucket by 100.
STEP-4).Customer request for API-
    if cap>=1 && <=100
        give the response 
    if req tokens >100
        served the 100 requests and calculate remaining requests and return the time in ms.
    if cap <1
        return the remaining time in ms from the timer intialized in the background.
Refilling Logic:- Add 10 tokens every second when the timer ends up until capacity <100.

 6. Walkthrough of Example Scenario
 T=0ms Bucket Initialized and customer requested 60 tokens
 T=0 ms 100-60 tokens remaining 
 T=2000ms Refill:-Refill: 40 + (2 × 10) = 60 tokens
 T=2000ms 70 requests arrive → 60 served, 10 denied
T=7000ms Refill: 0 + (5 × 10) = 50 tokens