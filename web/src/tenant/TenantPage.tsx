import { useQuery } from "@tanstack/react-query";
import { useLocation } from "@tanstack/react-router";

import { api } from "../api/client";
import { useBusiness } from "../api/business";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { PublicFooter } from "../landing/PublicFooter";
import { leasesCopy } from "../leases/copy";
import { chargeLabel, statusText } from "../leases/statementText";
import { limaToday } from "../leases/terms";
import { tenantCopy as text } from "./copy";

type Statement = components["schemas"]["TenantStatementResponse"];
type Refusal = keyof typeof text.errors;
type Loaded = { kind: "statement"; statement: Statement } | { kind: "refused"; refusal: Refusal };

const METHOD_LABELS: Record<string, string | undefined> = leasesCopy.payment.methods;
const REFUSALS = new Set<string>(["link_not_found", "portal_unavailable", "too_many_requests"]);

function itemClass(voided: boolean): string {
  return `flex flex-col gap-1 rounded-lg border border-stone-300 p-3 ${voided ? "text-stone-500" : ""}`;
}

function isRefusal(detail: unknown): detail is Refusal {
  return typeof detail === "string" && REFUSALS.has(detail);
}

async function fetchStatement(token: string): Promise<Loaded> {
  const { data, error } = await api.GET("/api/tenant/statement", {
    params: { header: { "x-tenant-token": token } },
  });
  if (data) {
    return { kind: "statement", statement: data };
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (isRefusal(detail)) {
    return { kind: "refused", refusal: detail };
  }
  throw new Error("Statement unavailable");
}

function Summary({ statement }: { statement: Statement }) {
  if (statement.balance_cents > 0) {
    return (
      <p className="rounded-lg bg-amber-50 p-4 text-xl font-semibold text-amber-900">
        {text.owes(formatSoles(statement.balance_cents))}
      </p>
    );
  }
  return (
    <p className="rounded-lg bg-green-50 p-4 text-xl font-semibold text-green-900">
      {statement.credit_cents > 0
        ? text.inFavor(formatSoles(statement.credit_cents))
        : text.upToDate}
    </p>
  );
}

function History({ statement }: { statement: Statement }) {
  const today = limaToday();
  return (
    <>
      <section aria-labelledby="tenant-charges" className="flex flex-col gap-3">
        <h2 id="tenant-charges" className="text-2xl font-bold">
          {text.charges}
        </h2>
        <ul className="flex flex-col gap-2">
          {[...statement.charges].reverse().map((charge, index) => (
            <li
              key={`${charge.due_date}-${String(index)}`}
              className={itemClass(charge.voided)}
            >
              <div className="flex justify-between gap-3">
                <span className="font-semibold">{chargeLabel(charge)}</span>
                <span>{formatSoles(Math.abs(charge.amount_cents))}</span>
              </div>
              <span className={charge.status === "overdue" ? "text-red-800" : "text-stone-700"}>
                {statusText(charge, today)}
              </span>
              {charge.partial && (
                <span className="text-stone-700">
                  {text.partial(
                    formatSoles(charge.amount_cents - charge.outstanding_cents),
                    formatSoles(charge.amount_cents),
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="tenant-payments" className="flex flex-col gap-3">
        <h2 id="tenant-payments" className="text-2xl font-bold">
          {text.payments}
        </h2>
        {statement.payments.length === 0 ? (
          <p>{text.noPayments}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {[...statement.payments].reverse().map((payment, index) => (
              <li
                key={`${payment.received_on}-${String(index)}`}
                className={itemClass(payment.voided)}
              >
                <div className="flex justify-between gap-3">
                  <span>{formatDay(payment.received_on)}</span>
                  <span className="font-semibold">{formatSoles(payment.amount_cents)}</span>
                </div>
                <span>
                  {METHOD_LABELS[payment.method] ?? payment.method}
                  {payment.voided && ` · ${leasesCopy.lease.voided}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function PrivacyNotice({ landlord }: { landlord: string }) {
  const business = useBusiness();
  return (
    <section
      aria-labelledby="tenant-privacy"
      className="flex flex-col gap-2 rounded-lg bg-stone-100 p-4"
    >
      <h2 id="tenant-privacy" className="text-xl font-bold">
        {text.privacyTitle}
      </h2>
      <p>
        {business.data
          ? text.privacy(landlord, business.data.privacy_inbox)
          : text.privacyWithoutInbox(landlord)}
      </p>
    </section>
  );
}

export function TenantPage() {
  const hash = useLocation({ select: (location) => location.hash });
  const token = new URLSearchParams(hash.replace(/^#/, "")).get("t") ?? "";
  const loaded = useQuery({
    queryKey: ["tenant-statement", token],
    queryFn: () => fetchStatement(token),
    enabled: token !== "",
  });
  const refusal: Refusal | null =
    token === "" ? "link_not_found" : loaded.data?.kind === "refused" ? loaded.data.refusal : null;
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.title}</h1>
      {refusal && <p role="alert">{text.errors[refusal]}</p>}
      {loaded.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {token !== "" && loaded.isPending && <p role="status">{text.loading}</p>}
      {loaded.data?.kind === "statement" && (
        <>
          <p>
            {text.greeting(
              loaded.data.statement.renter_name,
              loaded.data.statement.unit,
              loaded.data.statement.landlord_name,
            )}
          </p>
          <Summary statement={loaded.data.statement} />
          <History statement={loaded.data.statement} />
          <PrivacyNotice landlord={loaded.data.statement.landlord_name} />
        </>
      )}
      <PublicFooter />
    </div>
  );
}
