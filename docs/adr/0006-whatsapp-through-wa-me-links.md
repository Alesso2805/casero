# ADR-0006: WhatsApp through wa.me links only

- Status: Accepted
- Date: 2026-10-25
- Story: CS-01

## Context

Landlords collect rent through WhatsApp conversations. The WhatsApp Business API needs Meta approval and approved templates, and Meta charges per delivered message (including utility messages since 1 October 2026). Bots would send messages on the landlord's behalf to people who never agreed to receive them from Casero.

## Decision

- In the MVP Casero never sends WhatsApp messages. The "Enviar por WhatsApp" button opens `https://wa.me/<number>?text=<message>`. The number is the tenant's `phone_e164` without the `+`, and the message is URL-encoded. The landlord sends it from their own phone.
- **Templates:**
  - Three per account: `friendly`, `due_today` and `overdue`, with the variables `{inquilino}`, `{monto}`, `{periodo}`, `{fecha}` and `{enlace}`.
  - Until the landlord edits one, the default text from SPEC.md is used. A row in `message_templates` is created on the first edit.
- **`{enlace}`:**
  - It is always the lease's current tenant link. `reminders` obtains it from `tenant_portal` through a port (ADR-0001).
  - Regenerating the link makes earlier messages point to a revoked link, and the UI says so before regenerating.
- **Logging:** the server prepares the message and records the send with a server-generated `reminder_logs` row (kind `rent`, channel `whatsapp_link`) before returning the link, which the browser then opens. The panel shows "recordado hace N días".
- **Gating:** the button requires the `whatsapp_links` feature (through `entitlements`) and `leases.tools_enabled`.
- **Privacy:** the message contains a name, an amount and the tenant's link. Since CS-16 the server builds it from the account's templates (`{enlace}` needs the link, which only the server can sign). It travels only in the response to the landlord, with `Cache-Control: no-store`, and is never stored or logged. The browser sends no `wa.me` URL to error tracking.

## Consequences

- No cost, no Meta approval, and the tenant receives the message from someone they know.
- Casero cannot confirm delivery or reading: "recordado" means the button was used.
- Automatic reminders through the official API (CS-30, after launch) need a new ADR covering consent, templates and cost.

## Enforcement

- An architecture test that no WhatsApp API client or base URL other than `https://wa.me/` appears in the code.
- Frontend tests for encoding: accents, line breaks and the `+` sign.
