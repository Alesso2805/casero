# ADR-0009: Email through SMTP behind a Mailer port, sent by the worker at most once

- Status: Accepted
- Date: 2026-10-26
- Story: CS-04

## Context

Casero sends email through Amazon SES in production and Mailpit locally (SPEC.md, Correo). The first email is the copy of each complaint in the Libro de Reclamaciones. The regulation requires that copy to be sent automatically to the consumer (D.S. 011-2011-PCM, art. 4-B). Verification, recovery, tax reminders and the daily digest come later.

There are two constraints:

- The API process schedules no work (AR-07).
- Scheduled emails are recorded before they are sent and go out at most once (CLAUDE.md, rule 12).

## Decision

- **One SMTP adapter.** `shared.infrastructure.mail.SmtpMailer` sends a plain-text `Email` (`shared.kernel.email`) with `aiosmtplib`.
  - The same adapter talks to Mailpit (port 1025, no TLS) and to the SES SMTP endpoint (port 587, STARTTLS).
  - It sets `Date` from the injected `Clock` and its own `Message-ID`.
  - It raises `MailDeliveryError` with only the exception type as its code.
- **A port in each module.** Each module declares its own `Protocol` for the mailer in its `application` layer, as with every port (AR-03). The first one is `ComplaintMailer` in `admin`.
- **The worker sends complaint emails.** Each tick, `SendComplaintEmails` takes the complaints that have no `job_runs` row for `complaint_copy` (only those with an email) or `complaint_notice`.
  - For each one it inserts the `running` row and commits, then sends, then marks the row `done` or `failed`.
  - A failure or a crash between the commit and the send is never retried, so an email never goes out twice.
  - The consumer still has the sheet on screen with a print button, and failed jobs feed the alerts of CS-26.
- **No personal data in the notice.** The notice to the business inbox carries only the number, the kind, the deadline and the answer channel. The details stay in the database.
- **Logs.** The worker logs a crashed job by name and exception type only, because exception messages can carry personal data (rule 8).

## Consequences

- The copy arrives within about a minute of filing, not during the request.
- Switching from SES to another provider means changing environment variables only, as long as the provider offers SMTP.
- `List-Unsubscribe` headers and the suppression check before sending arrive with the scheduled emails and the SNS webhook. A complaint copy is transactional, so an unsubscribe never suppresses it.
- Using the SES HTTP API would remove the SMTP dependency but add the AWS SDK and a second adapter for Mailpit. This can be revisited if SMTP limits show up.
