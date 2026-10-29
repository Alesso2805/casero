import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";
import { useState } from "react";

import { secondaryButton, textLink } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { FIRST_CONTROL_PERIOD, limaToday, periodLabel } from "../leases/terms";
import { CompleteDocument } from "./CompleteDocument";
import { taxCopy as text } from "./copy";
import { SunatPayments } from "./SunatPayments";

type Month = components["schemas"]["MonthDeclarationsResponse"];
type Declaration = components["schemas"]["DeclarationResponse"];
type Loaded =
  | { kind: "month"; month: Month }
  | { kind: "login" }
  | { kind: "not_in_plan" }
  | { kind: "paused" }
  | { kind: "unknown_year" };

const CENTS_PER_SOL = 100;
const MONTHS_PER_YEAR = 12;

async function fetchDeclarations(period: string): Promise<Loaded> {
  const { data, error, response } = await api.GET("/api/app/tax/declarations", {
    params: { query: { period } },
  });
  if (data) {
    return { kind: "month", month: data };
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return detail === "tax_module_unavailable" ? { kind: "not_in_plan" } : { kind: "paused" };
  }
  if (response.status === 422 && detail === "unknown_year") {
    return { kind: "unknown_year" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function shiftMonth(period: string, months: number): string {
  const [year = 0, month = 1] = period.split("-").map(Number);
  const index = year * MONTHS_PER_YEAR + month - 1 + months;
  const shifted = (index % MONTHS_PER_YEAR) + 1;
  return `${String(Math.floor(index / MONTHS_PER_YEAR))}-${String(shifted).padStart(2, "0")}`;
}

function wholeSoles(cents: number): string {
  return String(cents / CENTS_PER_SOL);
}

function CopyRow({
  label,
  value,
  copyValue,
  onCopied,
}: {
  label: string;
  value: string;
  copyValue?: string;
  onCopied: (label: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-stone-200 py-2">
      <dt className="text-stone-700">{label}</dt>
      <dd className="flex min-h-11 items-center justify-between gap-3">
        <span className="font-semibold">{value}</span>
        {copyValue !== undefined && (
          <button
            type="button"
            className="min-h-11 rounded-lg border border-brand px-3 text-brand"
            aria-label={text.card.copyLabel(label)}
            onClick={() => {
              void navigator.clipboard.writeText(copyValue).then(() => {
                onCopied(label);
              });
            }}
          >
            {text.card.copy}
          </button>
        )}
      </dd>
    </div>
  );
}

function afterDeclaringText(declaration: Declaration, month: Month): string | null {
  const after = declaration.after_declaring;
  if (!after) {
    return null;
  }
  const period = periodLabel(month.period);
  switch (after.kind) {
    case "up":
      return text.after.up(
        formatSoles(after.base_difference_cents),
        period,
        formatSoles(after.tax_difference_cents),
      );
    case "down":
      return text.after.down(period);
    case "document_changed":
      return text.after.document_changed;
    case "overdue_unpaid":
      return text.after.overdue_unpaid(formatDay(month.due_on ?? ""));
  }
}

function DeclarationCard({ declaration, month }: { declaration: Declaration; month: Month }) {
  const [copied, setCopied] = useState("");
  const after = afterDeclaringText(declaration, month);
  const onCopied = (label: string) => {
    setCopied(text.card.copied(label));
  };
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-stone-300 p-4">
      <h3 className="text-xl font-semibold">{declaration.renter_name}</h3>
      {declaration.company_tenant && (
        <p className="text-stone-700">
          <span className="font-semibold">{text.card.company}.</span> {text.card.companyNotice}
        </p>
      )}
      {declaration.incomplete && (
        <p className="rounded-lg bg-amber-50 p-3 text-amber-900">
          {text.card.incomplete(declaration.renter_name)}
        </p>
      )}
      {declaration.incomplete && (
        <CompleteDocument renterId={declaration.renter_id} renterName={declaration.renter_name} />
      )}
      <dl>
        {month.ruc ? (
          <CopyRow label={text.card.ruc} value={month.ruc} copyValue={month.ruc} onCopied={onCopied} />
        ) : (
          <CopyRow label={text.card.ruc} value={text.card.noRuc} onCopied={onCopied} />
        )}
        <CopyRow label={text.card.period} value={periodLabel(month.period)} onCopied={onCopied} />
        {declaration.doc_type && declaration.doc_number && (
          <>
            <CopyRow
              label={text.card.docType}
              value={text.docTypes[declaration.doc_type]}
              onCopied={onCopied}
            />
            <CopyRow
              label={text.card.docNumber}
              value={declaration.doc_number}
              copyValue={declaration.doc_number}
              onCopied={onCopied}
            />
          </>
        )}
        <CopyRow label={text.card.propertyKind} value={text.card.property} onCopied={onCopied} />
        <CopyRow
          label={text.card.base}
          value={formatSoles(declaration.base_cents)}
          copyValue={wholeSoles(declaration.base_cents)}
          onCopied={onCopied}
        />
        <CopyRow
          label={text.card.tax}
          value={formatSoles(declaration.tax_cents)}
          copyValue={wholeSoles(declaration.tax_cents)}
          onCopied={onCopied}
        />
      </dl>
      <p role="status" className="text-stone-700">
        {copied}
      </p>
      <p className="text-stone-600">{text.card.collected(formatSoles(declaration.collected_cents))}</p>
      {declaration.old_debt_cents > 0 && (
        <p className="text-stone-700">{text.card.oldDebt(formatSoles(declaration.old_debt_cents))}</p>
      )}
      {after && <p className="rounded-lg bg-amber-50 p-3 text-amber-900">{after}</p>}
      {!declaration.incomplete && <SunatPayments declaration={declaration} period={month.period} />}
    </li>
  );
}

function DueNotice({ month }: { month: Month }) {
  switch (month.due_status) {
    case "known":
      return <p className="text-lg font-semibold">{text.due.known(formatDay(month.due_on ?? ""))}</p>;
    case "unknown_schedule":
      return <p>{text.due.unknownSchedule(month.period.slice(0, 4))}</p>;
    case "no_ruc":
      return (
        <p>
          {text.due.noRuc}{" "}
          <Link to="/app/mis-datos" className="text-brand underline">
            {text.due.goToProfile}
          </Link>
        </p>
      );
  }
}

function MonthDetails({ month }: { month: Month }) {
  const label = periodLabel(month.period);
  return (
    <>
      {month.declarations.length === 0 ? (
        <p>{text.empty(label)}</p>
      ) : (
        <>
          <div className="flex flex-col gap-1 rounded-lg bg-stone-100 p-4">
            <p className="text-xl font-semibold">
              {text.total(formatSoles(month.total_tax_cents), month.declarations.length)}
            </p>
            <DueNotice month={month} />
          </div>
          <ul className="flex flex-col gap-3">
            {month.declarations.map((declaration) => (
              <DeclarationCard
                key={declaration.renter_id}
                declaration={declaration}
                month={month}
              />
            ))}
          </ul>
        </>
      )}
      {month.minimum_rent.length > 0 && (
        <section aria-labelledby="minimum-rent-title" className="flex flex-col gap-2">
          <h2 id="minimum-rent-title" className="text-xl font-semibold">
            {text.minimumRent.title}
          </h2>
          {month.minimum_rent.map((property) => (
            <p key={property.property_id}>{text.minimumRent.line(property.property_name)}</p>
          ))}
          <p className="text-stone-700">{text.minimumRent.explain}</p>
        </section>
      )}
      {month.untaxed.length > 0 && (
        <section aria-labelledby="untaxed-title" className="flex flex-col gap-2">
          <h2 id="untaxed-title" className="text-xl font-semibold">
            {text.untaxed.title}
          </h2>
          {month.untaxed.map((lease) => (
            <p key={lease.lease_id}>
              {text.untaxed.line(lease.renter_name, formatSoles(lease.collected_cents))}
            </p>
          ))}
          <p className="text-stone-700">{text.untaxed.explain}</p>
        </section>
      )}
    </>
  );
}

function AccountantExports({ year }: { year: string }) {
  return (
    <section aria-labelledby="accountant-title" className="flex flex-col gap-2">
      <h2 id="accountant-title" className="text-xl font-semibold">
        {text.accountant.title}
      </h2>
      <p>{text.accountant.intro}</p>
      <a href={`/api/app/exports/payments.csv?year=${year}`} download className={textLink}>
        {text.accountant.payments(year)}
      </a>
      <a href={`/api/app/exports/declarations.csv?year=${year}`} download className={textLink}>
        {text.accountant.declarations(year)}
      </a>
    </section>
  );
}

function HowToPay() {
  return (
    <section aria-labelledby="how-to-title" className="flex flex-col gap-2">
      <h2 id="how-to-title" className="text-xl font-semibold">
        {text.howTo.title}
      </h2>
      <ol className="flex list-decimal flex-col gap-1 pl-6">
        {text.howTo.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="font-semibold">{text.howTo.neverSol}</p>
    </section>
  );
}

export function DeclarationsPage() {
  const current = limaToday().slice(0, 7);
  const [period, setPeriod] = useState(() => {
    const previous = shiftMonth(current, -1);
    return previous < FIRST_CONTROL_PERIOD ? current : previous;
  });
  const loaded = useQuery({
    queryKey: ["declarations", period],
    queryFn: () => fetchDeclarations(period),
  });

  if (loaded.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.title}</h1>
      <p>{text.intro}</p>
      <h2 className="text-2xl font-semibold">{text.month(periodLabel(period))}</h2>
      <nav aria-label={text.month(periodLabel(period))} className="grid grid-cols-2 gap-3">
        <button
          type="button"
          className={secondaryButton}
          disabled={period <= FIRST_CONTROL_PERIOD}
          onClick={() => {
            setPeriod(shiftMonth(period, -1));
          }}
        >
          {text.previousMonth}
        </button>
        <button
          type="button"
          className={secondaryButton}
          disabled={period >= current}
          onClick={() => {
            setPeriod(shiftMonth(period, 1));
          }}
        >
          {text.nextMonth}
        </button>
      </nav>
      {loaded.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {loaded.isPending && <p role="status">{text.loading}</p>}
      {loaded.data?.kind === "month" && <MonthDetails month={loaded.data.month} />}
      {loaded.data?.kind === "month" && <AccountantExports year={period.slice(0, 4)} />}
      {loaded.data?.kind === "not_in_plan" && <p>{text.notInPlan}</p>}
      {loaded.data?.kind === "unknown_year" && <p>{text.unknownYear(period.slice(0, 4))}</p>}
      {loaded.data?.kind === "paused" && (
        <p>
          {text.paused}{" "}
          <Link to="/app" className="text-brand underline">
            {text.goHome}
          </Link>
        </p>
      )}
      <HowToPay />
      <p className="text-stone-600">{text.disclaimer}</p>
      <Link to="/app" className={textLink}>
        {text.goHome}
      </Link>
    </div>
  );
}
