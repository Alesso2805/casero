# ADR-0011: Error tracking without personal data

- Status: Accepted
- Date: 2026-10-28
- Story: CS-26

## Context

SPEC requires error tracking with Sentry (free plan, US region) for the API, the worker and the frontend, with a filter that removes personal data. CLAUDE.md rule 8 forbids names, documents, phones, emails, tokens and amounts tied to a person in logs, errors and URLs.

Error payloads leak in several places:

- Database errors quote the offending values ("Key (email)=(…)").
- Local variables hold request data.
- Breadcrumbs hold log lines and SQL.
- The browser's URL can carry the tenant token in its fragment (`/i#t=…`).

The CSP allows `connect-src 'self'` only.

## Decision

### API and worker

- `sentry-sdk` starts only when `SENTRY_DSN` is set, so local development and CI never send anything.
- No performance tracing, no breadcrumbs, no local variables, and default PII stays off.
- `before_send` keeps the request's method and URL path only. It drops headers, cookies, bodies, query strings, the user and `extra`, and it empties every exception message. What remains points at the code: exception types and stack frames.
- The API's `ErrorShield` (ADR-0007) sends each unhandled exception once, with its stack, and logs only its type.
- A structlog processor turns every other error-level log event into a Sentry message tagged with the event's fields. Those fields are already free of personal data, because logs carry only safe fields and `drop_personal_fields` removes the known ones. This is how `worker.job_crashed`, `worker.account_job_failed` and `complaint_email.failed` reach Sentry.

### Browser

- The web app does not load the Sentry SDK.
- A small listener sends each unhandled error to `POST /api/public/client-errors` with three fields:
  - its type, such as `TypeError`;
  - the route, as `location.pathname` only;
  - the code location, as script path, line and column.
- The listener stops after 5 reports per page.
- The endpoint is rate-limited per client (30 per hour) and refuses any route or location containing `?` or `#`.
- The API forwards each report to Sentry as a message.
- Unknown routes and render errors show Spanish pages, and render errors are reported the same way.

## Consequences

- The CSP keeps `connect-src 'self'`.
- The page never talks to a third party, and the bundle does not grow.
- Neither a message a person typed nor the tenant token can leave the browser through error reports.
- Browser reports have no full stack trace or source maps, so a browser bug is debugged by reproducing it from its route and code location.
- Sentry's server-side data scrubbing is turned on in the project settings as a second layer (`docs/ops/server.md`).

## Enforcement

- Unit tests:
  - scrubbing removes request data, the user, breadcrumbs, messages and local variables;
  - an unhandled API error is sent once with its type and stack and without its message;
  - error logs arrive as tagged messages.
- Integration tests: the client errors endpoint forwards type, route and location, refuses reports carrying `?` or `#`, and is rate-limited.
- Frontend tests: a report never includes the URL fragment or the error message.
