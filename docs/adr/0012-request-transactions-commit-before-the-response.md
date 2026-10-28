# ADR-0012: Request transactions commit before the response

- Status: Accepted
- Date: 2026-10-28
- Story: critical review of Sprints 4–6 (I13)

## Context

Every API request runs in one database transaction, opened by the `anonymous_transaction` dependency and shared by `current_account`, which sets `app.account_id` in it (ADR-0002).

A dependency with `yield` has FastAPI's default `"request"` scope. That scope ends after the response has been sent, so the commit happens after the client already has its answer. As a result:

- A `201` for a payment or a lease can reach the phone before the row is durable. If the commit then fails, the client has already discarded the id it generated (CLAUDE.md, rule 5), and the landlord believes the payment was saved.
- The lease page reloads the statement right after a write, and that read can miss the write.
- The lock on the account row, taken to check the plan limit, outlives the request.

## Decision

- The transaction dependency uses the `"function"` scope through one shared alias, `Transaction` in `shared/infrastructure/database.py`. With this scope the dependency ends, and the transaction commits or rolls back, after the path operation returns and before the response is sent. A `2xx` therefore means the write is durable.
- Every use goes through that alias. FastAPI caches dependencies by callable and scope, so mixing scopes would open a second transaction, and that transaction would have no `app.account_id`.

## Consequences

Two tests guard the decision:

- `tests/unit/test_transactions.py` drives an app through ASGI and checks that the commit comes before `http.response.start`.
- A second test checks that every route opens its transaction with the `"function"` scope.

A response that fails after the path operation returns (for example, while it is being sent) no longer rolls the write back. That is the intended trade-off: the client retries with the same id and gets the existing row.
