import { type ReactNode, useEffect, useRef, useState } from "react";

import { primaryButton, secondaryButton } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { parseSolesToCents } from "../landing/money";
import { leasesCopy as text } from "./copy";
import { limaToday, uuidv7 } from "./terms";
import { inputClass, type Outcome, outcomeOf, useLeaseWrite } from "./writes";

type Lease = components["schemas"]["LeaseResponse"];
type Statement = components["schemas"]["StatementResponse"];
type ChargeLine = components["schemas"]["ChargeLineResponse"];
type Action = "rent" | "end" | "terminate" | "prior";

const FIRST_DEBT_MONTH = "2026-01";
const t = text.leaseActions;
const REFUSALS: Record<string, string | undefined> = {
  lease_ended: t.errors.ended,
  end_in_past: t.errors.endInPast,
  end_in_future: t.errors.endInFuture,
  end_before_start: text.errors.endBeforeStart,
  end_before_control: t.errors.endBeforeControl,
  prior_debt_exists: t.errors.priorExists,
  balance_2026_without_months: text.errors.balance2026,
};

export function priorDebtEras(lease: Lease, charges: ChargeLine[]): boolean[] {
  const recorded = (pre2026: boolean) =>
    charges.some((c) => c.kind === "opening_balance" && c.pre_2026 === pre2026 && !c.voided);
  const startMonth = lease.start_date.slice(0, 7);
  const firstDebtMonth = startMonth > FIRST_DEBT_MONTH ? startMonth : FIRST_DEBT_MONTH;
  return [
    ...(startMonth < FIRST_DEBT_MONTH && !recorded(true) ? [true] : []),
    ...(firstDebtMonth < lease.control_from_period && !recorded(false) ? [false] : []),
  ];
}

function problemOf(failed: boolean, outcome: Outcome | undefined): string | null {
  if (failed || outcome?.kind === "conflict") {
    return text.errors.failure;
  }
  if (outcome?.kind === "refused") {
    return REFUSALS[outcome.detail] ?? text.errors.failure;
  }
  return null;
}

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-stone-600">
          {hint}
        </p>
      )}
      {children}
    </div>
  );
}

function ActionForm({
  id,
  title,
  submit,
  ready,
  pending,
  problem,
  onSubmit,
  onCancel,
  children,
}: {
  id: string;
  title: string;
  submit: string;
  ready: boolean;
  pending: boolean;
  problem: string | null;
  onSubmit: () => void;
  onCancel: () => void;
  children: ReactNode;
}) {
  return (
    <form
      noValidate
      aria-labelledby={`${id}-title`}
      className="flex flex-col gap-4 rounded-lg border border-stone-300 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <h3 id={`${id}-title`} className="text-xl font-bold">
        {title}
      </h3>
      {children}
      {problem && (
        <p role="alert" className="text-red-800">
          {problem}
        </p>
      )}
      <button type="submit" className={primaryButton} disabled={!ready || pending}>
        {submit}
      </button>
      <button type="button" className={secondaryButton} onClick={onCancel}>
        {t.cancel}
      </button>
    </form>
  );
}

function useFirstField() {
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    first.current?.focus();
  }, []);
  return first;
}

interface FormProps {
  lease: Lease;
  onDone: (message: string) => void;
  onCancel: () => void;
}

function RentForm({ lease, onDone, onCancel }: FormProps) {
  const [amount, setAmount] = useState("");
  const [id] = useState(uuidv7);
  const first = useFirstField();
  const cents = parseSolesToCents(amount) ?? 0;
  const saving = useLeaseWrite(lease.id, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/rent-changes", {
        params: { path: { lease_id: lease.id } },
        body: { id, monthly_rent_cents: cents },
      }),
    ),
  );
  return (
    <ActionForm
      id="rent-change"
      title={t.rent}
      submit={t.save}
      ready={cents > 0}
      pending={saving.isPending}
      problem={problemOf(saving.isError, saving.data)}
      onSubmit={() => {
        saving.mutate(undefined, {
          onSuccess: (outcome) => {
            if (outcome.kind === "done") onDone(t.rentSaved);
          },
        });
      }}
      onCancel={onCancel}
    >
      <Field id="rent-amount" label={t.rentAmount} hint={t.rentHint}>
        <input
          id="rent-amount"
          ref={first}
          inputMode="decimal"
          aria-describedby="rent-amount-hint"
          className={inputClass}
          value={amount}
          onChange={(event) => {
            setAmount(event.target.value);
          }}
        />
      </Field>
    </ActionForm>
  );
}

function EndDateForm({ lease, onDone, onCancel }: FormProps) {
  const [endDate, setEndDate] = useState(lease.end_date ?? "");
  const first = useFirstField();
  const saving = useLeaseWrite(lease.id, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/end-date", {
        params: { path: { lease_id: lease.id } },
        body: { end_date: endDate || null },
      }),
    ),
  );
  return (
    <ActionForm
      id="end-date"
      title={t.end}
      submit={t.save}
      ready
      pending={saving.isPending}
      problem={problemOf(saving.isError, saving.data)}
      onSubmit={() => {
        saving.mutate(undefined, {
          onSuccess: (outcome) => {
            if (outcome.kind === "done") onDone(t.endSaved);
          },
        });
      }}
      onCancel={onCancel}
    >
      <Field id="end-date-value" label={t.endDate} hint={t.endHint}>
        <input
          id="end-date-value"
          ref={first}
          type="date"
          aria-describedby="end-date-value-hint"
          className={inputClass}
          value={endDate}
          onChange={(event) => {
            setEndDate(event.target.value);
          }}
        />
      </Field>
    </ActionForm>
  );
}

function NotStartedNote() {
  const note = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    note.current?.focus();
  }, []);
  return (
    <p ref={note} tabIndex={-1}>
      {t.terminateNotStarted}
    </p>
  );
}

function TerminationForm({ lease, onDone, onCancel }: FormProps) {
  const [today] = useState(limaToday);
  const [endedOn, setEndedOn] = useState(today);
  const [credit, setCredit] = useState("");
  const [creditId] = useState(uuidv7);
  const first = useFirstField();
  const notStarted = lease.start_date > today;
  const creditCents = notStarted ? 0 : (parseSolesToCents(credit) ?? 0);
  const saving = useLeaseWrite(lease.id, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/termination", {
        params: { path: { lease_id: lease.id } },
        body: {
          ended_on: notStarted ? today : endedOn,
          credit: creditCents > 0 ? { id: creditId, amount_cents: creditCents } : null,
        },
      }),
    ),
  );
  const fieldsReady = endedOn !== "" && (credit.trim() === "" || creditCents > 0);
  return (
    <ActionForm
      id="termination"
      title={t.terminate}
      submit={t.terminateConfirm}
      ready={notStarted || fieldsReady}
      pending={saving.isPending}
      problem={problemOf(saving.isError, saving.data)}
      onSubmit={() => {
        saving.mutate(undefined, {
          onSuccess: (outcome) => {
            if (outcome.kind === "done") onDone(t.terminated);
          },
        });
      }}
      onCancel={onCancel}
    >
      {notStarted ? (
        <NotStartedNote />
      ) : (
        <>
          <Field id="termination-date" label={t.terminateDate} hint={t.terminateHint}>
            <input
              id="termination-date"
              ref={first}
              type="date"
              aria-describedby="termination-date-hint"
              className={inputClass}
              value={endedOn}
              onChange={(event) => {
                setEndedOn(event.target.value);
              }}
            />
          </Field>
          <Field id="termination-credit" label={t.credit}>
            <input
              id="termination-credit"
              inputMode="decimal"
              className={inputClass}
              value={credit}
              onChange={(event) => {
                setCredit(event.target.value);
              }}
            />
          </Field>
        </>
      )}
    </ActionForm>
  );
}

function PriorDebtForm({
  lease,
  eras,
  onDone,
  onCancel,
}: FormProps & { eras: boolean[] }) {
  const [pre2026, setPre2026] = useState(eras[0] ?? false);
  const [amount, setAmount] = useState("");
  const [id] = useState(uuidv7);
  const first = useFirstField();
  const cents = parseSolesToCents(amount) ?? 0;
  const saving = useLeaseWrite(lease.id, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/charges/prior-debts", {
        params: { path: { lease_id: lease.id } },
        body: { id, pre_2026: pre2026, amount_cents: cents },
      }),
    ),
  );
  return (
    <ActionForm
      id="prior-debt"
      title={t.prior}
      submit={t.save}
      ready={cents > 0}
      pending={saving.isPending}
      problem={problemOf(saving.isError, saving.data)}
      onSubmit={() => {
        saving.mutate(undefined, {
          onSuccess: (outcome) => {
            if (outcome.kind === "done") onDone(t.priorSaved);
          },
        });
      }}
      onCancel={onCancel}
    >
      {eras.length === 1 && <p className="font-medium">{pre2026 ? t.priorPre2026 : t.prior2026}</p>}
      {eras.length > 1 && (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 font-medium">{t.priorEra}</legend>
          {eras.map((era) => (
            <label key={String(era)} className="flex min-h-11 items-center gap-3">
              <input
                type="radio"
                name="prior-debt-era"
                className="h-5 w-5"
                checked={pre2026 === era}
                onChange={() => {
                  setPre2026(era);
                }}
              />
              {era ? t.priorPre2026 : t.prior2026}
            </label>
          ))}
        </fieldset>
      )}
      <Field id="prior-debt-amount" label={t.priorAmount} hint={t.priorHint}>
        <input
          id="prior-debt-amount"
          ref={first}
          inputMode="decimal"
          aria-describedby="prior-debt-amount-hint"
          className={inputClass}
          value={amount}
          onChange={(event) => {
            setAmount(event.target.value);
          }}
        />
      </Field>
    </ActionForm>
  );
}

function Refund({
  lease,
  creditCents,
  onDone,
}: {
  lease: Lease;
  creditCents: number;
  onDone: (message: string) => void;
}) {
  const [id] = useState(uuidv7);
  const saving = useLeaseWrite(lease.id, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/charges/adjustments", {
        params: { path: { lease_id: lease.id } },
        body: { id, amount_cents: creditCents },
      }),
    ),
  );
  const problem = problemOf(saving.isError, saving.data);
  return (
    <div className="flex flex-col gap-2">
      <p>{t.refundHint}</p>
      <button
        type="button"
        className={primaryButton}
        disabled={saving.isPending}
        onClick={() => {
          saving.mutate(undefined, {
            onSuccess: (outcome) => {
              if (outcome.kind === "done") onDone(t.refundSaved);
            },
          });
        }}
      >
        {t.refund}
      </button>
      {problem && (
        <p role="alert" className="text-red-800">
          {problem}
        </p>
      )}
    </div>
  );
}

export function LeaseActions({
  lease,
  statement,
  onDone,
}: {
  lease: Lease;
  statement: Statement;
  onDone: (message: string) => void;
}) {
  const [open, setOpen] = useState<Action | null>(null);
  const returnTo = useRef<Action | null>(null);
  useEffect(() => {
    if (open === null && returnTo.current) {
      document.getElementById(`lease-action-${returnTo.current}`)?.focus();
      returnTo.current = null;
    }
  }, [open]);
  const eras = priorDebtEras(lease, statement.charges);
  const active = lease.ended_at === null;
  const done = (message: string) => {
    setOpen(null);
    onDone(message);
  };
  const close = () => {
    returnTo.current = open;
    setOpen(null);
  };
  const offered: { action: Action; label: string }[] = [
    ...(active
      ? [
          { action: "rent" as const, label: t.rent },
          { action: "end" as const, label: t.end },
          { action: "terminate" as const, label: t.terminate },
        ]
      : []),
    ...(eras.length > 0 ? [{ action: "prior" as const, label: t.prior }] : []),
  ];
  const refund = !active && statement.credit_cents > 0;
  if (offered.length === 0 && !refund) {
    return null;
  }
  const props = { lease, onDone: done, onCancel: close };
  return (
    <section aria-labelledby="lease-actions-title" className="flex flex-col gap-3">
      <h2 id="lease-actions-title" className="text-2xl font-bold">
        {t.title}
      </h2>
      {refund && <Refund lease={lease} creditCents={statement.credit_cents} onDone={onDone} />}
      {open === "rent" && <RentForm {...props} />}
      {open === "end" && <EndDateForm {...props} />}
      {open === "terminate" && <TerminationForm {...props} />}
      {open === "prior" && <PriorDebtForm {...props} eras={eras} />}
      {open === null &&
        offered.map(({ action, label }) => (
          <button
            key={action}
            id={`lease-action-${action}`}
            type="button"
            className={secondaryButton}
            onClick={() => {
              setOpen(action);
            }}
          >
            {label}
          </button>
        ))}
    </section>
  );
}
