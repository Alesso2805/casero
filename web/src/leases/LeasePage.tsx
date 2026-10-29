import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  primaryButton,
  secondaryButton,
  SelectField,
  TextField,
  textLink,
} from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles, parseSolesToCents } from "../landing/money";
import { AdjustmentForm, ChargeActions } from "./ChargeActions";
import { LeaseActions } from "./LeaseActions";
import { SunatVoidNotice } from "./SunatVoidNotice";
import { chargeLabel, statusText } from "./statementText";
import { TenantLinkBlock } from "./TenantLinkBlock";
import { fetchProperties } from "../properties/PropertiesPage";
import { remindersCopy } from "../reminders/copy";
import { WhatsAppButton } from "../reminders/WhatsAppButton";
import { leasesCopy as text } from "./copy";
import { fetchLeases, fetchRenters } from "./LeasesPage";
import { limaToday, uuidv7 } from "./terms";

type Statement = components["schemas"]["StatementResponse"];
type ChargeLine = components["schemas"]["ChargeLineResponse"];
type PaymentLine = components["schemas"]["PaymentResponse"];
type Method = components["schemas"]["PaymentRequest"]["method"];
type Loaded =
  | { kind: "statement"; statement: Statement }
  | { kind: "login" }
  | { kind: "paused" }
  | { kind: "missing" };

const METHODS = ["cash", "yape", "plin", "transfer", "bank_deposit"] as const satisfies Method[];
const METHOD_LABELS: Record<string, string | undefined> = text.payment.methods;

function itemClass(voided: boolean): string {
  return `flex flex-col rounded-lg border border-stone-300 p-3 ${voided ? "text-stone-500" : ""}`;
}

async function fetchStatement(leaseId: string): Promise<Loaded> {
  const { data, response } = await api.GET("/api/app/leases/{lease_id}/statement", {
    params: { path: { lease_id: leaseId } },
  });
  if (data) {
    return { kind: "statement", statement: data };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return { kind: "paused" };
  }
  if (response.status === 404) {
    return { kind: "missing" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function hasUnpaidRent(statement: Statement): boolean {
  return statement.charges.some(
    (line) =>
      (line.kind === "rent" || line.kind === "rent_correction") &&
      line.status !== null &&
      line.status !== "paid",
  );
}

function Summary({ statement, ended }: { statement: Statement; ended: boolean }) {
  if (statement.balance_cents > 0) {
    return (
      <p className="rounded-lg bg-amber-50 p-4 text-xl font-semibold text-amber-900">
        {text.lease.owes(formatSoles(statement.balance_cents))}
      </p>
    );
  }
  return (
    <p className="rounded-lg bg-green-50 p-4 text-xl font-semibold text-green-900">
      {statement.credit_cents <= 0
        ? text.lease.upToDate
        : (ended ? text.lease.toReturn : text.lease.inFavor)(formatSoles(statement.credit_cents))}
    </p>
  );
}

function Charges({
  charges,
  today,
  leaseId,
}: {
  charges: ChargeLine[];
  today: string;
  leaseId: string;
}) {
  const corrected = new Set(charges.map((charge) => charge.corrects_charge_id));
  return (
    <ul className="flex flex-col gap-2">
      {[...charges].reverse().map((charge) => (
        <li
          key={charge.id}
          className={`${itemClass(charge.voided)} gap-1`}
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
              {text.lease.partial(
                formatSoles(charge.amount_cents - charge.outstanding_cents),
                formatSoles(charge.amount_cents),
              )}
            </span>
          )}
          <ChargeActions
            charge={charge}
            label={chargeLabel(charge)}
            leaseId={leaseId}
            corrected={corrected.has(charge.id)}
          />
        </li>
      ))}
    </ul>
  );
}

const paymentSchema = z.object({
  amount: z
    .string()
    .trim()
    .refine((value) => (parseSolesToCents(value) ?? 0) > 0, { error: text.errors.amount }),
  receivedOn: z.string().min(1, text.errors.required),
  method: z.enum(METHODS, { error: text.errors.required }),
  note: z.string().trim().max(200),
});

type PaymentValues = z.input<typeof paymentSchema>;
interface Notice {
  message: string;
  bankThreshold: number | null;
  beforeControl: boolean;
}
type Saved =
  | ({ kind: "saved" } & Omit<Notice, "message">)
  | { kind: "refused"; detail: string }
  | { kind: "conflict" }
  | { kind: "login" };

const RECEIPT_ERRORS: Record<string, string> = {
  received_in_future: text.errors.receivedInFuture,
  received_before_2026: text.errors.receivedBefore2026,
};

function PaymentForm({
  leaseId,
  paymentId,
  onSaved,
  onConflict,
  onCancel,
}: {
  leaseId: string;
  paymentId: string;
  onSaved: (notice: Notice) => void;
  onConflict: () => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [conflict, setConflict] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    setFocus,
    formState: { errors },
  } = useForm<PaymentValues>({
    resolver: zodResolver(paymentSchema),
    defaultValues: { amount: "", receivedOn: limaToday(), note: "" },
  });
  useEffect(() => {
    setFocus("amount");
  }, [setFocus]);
  const mutation = useMutation({
    mutationFn: async (values: PaymentValues): Promise<Saved> => {
      const { data, error, response } = await api.POST("/api/app/leases/{lease_id}/payments", {
        params: { path: { lease_id: leaseId } },
        body: {
          id: paymentId,
          amount_cents: parseSolesToCents(values.amount) ?? 0,
          received_on: values.receivedOn,
          method: values.method,
          note: values.note.trim() || null,
        },
      });
      if (data) {
        return {
          kind: "saved",
          bankThreshold: data.bank_threshold_cents,
          beforeControl: data.before_control,
        };
      }
      if (response.status === 401) {
        return { kind: "login" };
      }
      if (response.status === 409) {
        return { kind: "conflict" };
      }
      const detail = (error as { detail?: unknown } | undefined)?.detail;
      if (typeof detail === "string" && Object.hasOwn(RECEIPT_ERRORS, detail)) {
        return { kind: "refused", detail };
      }
      throw new Error("Payment not saved");
    },
    // A lost response may hide a saved payment, so the list reloads whatever happened.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["statement", leaseId] }),
    onSuccess: (result) => {
      switch (result.kind) {
        case "saved":
          onSaved({
            message: text.payment.saved,
            bankThreshold: result.bankThreshold,
            beforeControl: result.beforeControl,
          });
          return;
        case "refused":
          setError("receivedOn", { message: RECEIPT_ERRORS[result.detail] ?? text.errors.failure });
          return;
        case "conflict":
          setConflict(true);
          onConflict();
          return;
        case "login":
          void navigate({ to: "/ingresar" });
      }
    },
  });
  return (
    <form
      noValidate
      aria-labelledby="payment-title"
      className="flex flex-col gap-4 rounded-lg border border-stone-300 p-4"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          setConflict(false);
          mutation.mutate(values);
        })(event);
      }}
    >
      <h2 id="payment-title" className="text-2xl font-bold">
        {text.payment.title}
      </h2>
      <TextField
        id="payment-amount"
        label={text.payment.amount}
        decimal
        autoComplete="off"
        error={errors.amount}
        registration={register("amount")}
      />
      <TextField
        id="payment-date"
        type="date"
        label={text.payment.receivedOn}
        hint={text.payment.receivedOnHint}
        error={errors.receivedOn}
        registration={register("receivedOn")}
      />
      <SelectField
        id="payment-method"
        label={text.payment.method}
        error={errors.method}
        registration={register("method")}
      >
        <option value="" />
        {METHODS.map((method) => (
          <option key={method} value={method}>
            {text.payment.methods[method]}
          </option>
        ))}
      </SelectField>
      <TextField
        id="payment-note"
        label={text.payment.note}
        autoComplete="off"
        error={errors.note}
        registration={register("note")}
      />
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {conflict && (
        <p role="alert" className="text-red-800">
          {text.payment.conflict}
        </p>
      )}
      <button type="submit" disabled={mutation.isPending} className={primaryButton}>
        {mutation.isPending ? text.payment.sending : text.payment.submit}
      </button>
      <button type="button" className={secondaryButton} onClick={onCancel}>
        {text.payment.cancel}
      </button>
    </form>
  );
}

function PaymentRow({ payment, leaseId }: { payment: PaymentLine; leaseId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [voiding, setVoiding] = useState(false);
  const [reason, setReason] = useState("");
  const row = useRef<HTMLLIElement>(null);
  const mutation = useMutation({
    mutationFn: async () => {
      const { data, response } = await api.POST("/api/app/payments/{payment_id}/void", {
        params: { path: { payment_id: payment.id } },
        body: { reason: reason.trim() },
      });
      if (response.status === 401) {
        return "login";
      }
      if (!data) {
        throw new Error("Payment not voided");
      }
      return data.paid_to_sunat;
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["statement", leaseId] }),
    onSuccess: (result) => {
      if (result === "login") {
        void navigate({ to: "/ingresar" });
        return;
      }
      row.current?.focus();
    },
  });
  const reasonId = `void-reason-${payment.id}`;
  return (
    <li ref={row} tabIndex={-1} className={`${itemClass(payment.voided)} gap-2`}>
      <div className="flex justify-between gap-3">
        <span>{formatDay(payment.received_on)}</span>
        <span className="font-semibold">{formatSoles(payment.amount_cents)}</span>
      </div>
      <span>
        {METHOD_LABELS[payment.method] ?? payment.method}
        {payment.note && ` · ${payment.note}`}
      </span>
      {payment.voided ? (
        <>
          <span>{text.lease.voided}</span>
          {Array.isArray(mutation.data) && <SunatVoidNotice periods={mutation.data} />}
        </>
      ) : voiding ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={reasonId}>{text.payment.voidReason}</label>
          <input
            id={reasonId}
            className="min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base"
            maxLength={200}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
          <div className="flex gap-3">
            <button
              type="button"
              className={primaryButton}
              disabled={reason.trim() === "" || mutation.isPending}
              onClick={() => {
                mutation.mutate();
              }}
            >
              {text.payment.voidConfirm}
            </button>
            <button
              type="button"
              className={secondaryButton}
              onClick={() => {
                setVoiding(false);
              }}
            >
              {text.payment.cancel}
            </button>
          </div>
          {mutation.isError && (
            <p role="alert" className="text-red-800">
              {text.errors.failure}
            </p>
          )}
        </div>
      ) : (
        <button
          type="button"
          className={`${secondaryButton} self-start`}
          onClick={() => {
            setVoiding(true);
          }}
        >
          {text.payment.void}
        </button>
      )}
    </li>
  );
}

export function LeasePage() {
  const { leaseId } = useParams({ from: "/app/contratos/$leaseId" });
  const statement = useQuery({
    queryKey: ["statement", leaseId],
    queryFn: () => fetchStatement(leaseId),
  });
  const leases = useQuery({ queryKey: ["leases"], queryFn: fetchLeases });
  const renters = useQuery({ queryKey: ["renters"], queryFn: fetchRenters });
  const properties = useQuery({ queryKey: ["properties"], queryFn: fetchProperties });
  // Kept until a save is confirmed: reopening after a lost response replays the same payment.
  const [draftId, setDraftId] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [adjustmentId, setAdjustmentId] = useState<string | null>(null);
  const [adjusting, setAdjusting] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const noticeBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    noticeBox.current?.focus();
  }, [notice]);

  if (statement.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  const lease =
    leases.data?.kind === "data" ? leases.data.data.find((l) => l.id === leaseId) : undefined;
  const renter =
    renters.data?.kind === "data" && lease
      ? renters.data.data.find((r) => r.id === lease.renter_id)
      : undefined;
  const unit =
    properties.data?.kind === "properties" && lease
      ? properties.data.properties
          .flatMap((p) => p.units.map((u) => ({ name: `${u.name} · ${p.name}`, id: u.id })))
          .find((u) => u.id === lease.unit_id)
      : undefined;
  const today = limaToday();
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <div className="flex flex-col gap-1">
        <h1 className="text-3xl font-bold">{renter?.full_name ?? text.list.unknownRenter}</h1>
        {unit && <p className="text-stone-700">{unit.name}</p>}
      </div>
      {statement.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {statement.data?.kind === "paused" && <p role="alert">{text.errors.paused}</p>}
      {statement.isPending && <p role="status">{text.lease.loading}</p>}
      {statement.data?.kind === "missing" && <p role="alert">{text.lease.missing}</p>}
      {statement.data?.kind === "statement" && (
        <>
          <Summary statement={statement.data.statement} ended={Boolean(lease?.ended_at)} />
          {notice && (
            <div
              ref={noticeBox}
              role="status"
              tabIndex={-1}
              className="flex flex-col gap-2 rounded-lg bg-stone-100 p-4"
            >
              <p>{notice.message}</p>
              {notice.bankThreshold !== null && (
                <p className="text-amber-900">
                  {text.payment.bank(formatSoles(notice.bankThreshold))}
                </p>
              )}
              {notice.beforeControl && (
                <p className="text-amber-900">{text.payment.beforeControl}</p>
              )}
            </div>
          )}
          {recording && draftId !== null ? (
            <PaymentForm
              leaseId={leaseId}
              paymentId={draftId}
              onSaved={(saved) => {
                setRecording(false);
                setDraftId(null);
                setNotice(saved);
              }}
              onConflict={() => {
                setDraftId(uuidv7());
              }}
              onCancel={() => {
                setRecording(false);
              }}
            />
          ) : (
            <button
              type="button"
              className={primaryButton}
              onClick={() => {
                setNotice(null);
                setDraftId((id) => id ?? uuidv7());
                setRecording(true);
              }}
            >
              {text.lease.record}
            </button>
          )}
          {hasUnpaidRent(statement.data.statement) && (
            <div className="flex flex-col gap-2">
              <WhatsAppButton
                leaseId={leaseId}
                renterName={renter?.full_name ?? text.list.unknownRenter}
              />
              <p className="text-stone-600">{remindersCopy.hint}</p>
            </div>
          )}
          {adjusting && adjustmentId !== null ? (
            <AdjustmentForm
              leaseId={leaseId}
              adjustmentId={adjustmentId}
              onSaved={() => {
                setAdjusting(false);
                setAdjustmentId(null);
                setNotice({
                  message: text.adjustment.saved,
                  bankThreshold: null,
                  beforeControl: false,
                });
              }}
              onConflict={() => {
                setAdjustmentId(uuidv7());
              }}
              onCancel={() => {
                setAdjusting(false);
              }}
            />
          ) : (
            <button
              type="button"
              className={secondaryButton}
              onClick={() => {
                setNotice(null);
                setAdjustmentId((id) => id ?? uuidv7());
                setAdjusting(true);
              }}
            >
              {text.adjustment.add}
            </button>
          )}
          <section aria-labelledby="charges-title" className="flex flex-col gap-3">
            <h2 id="charges-title" className="text-2xl font-bold">
              {text.lease.charges}
            </h2>
            <Charges charges={statement.data.statement.charges} today={today} leaseId={leaseId} />
          </section>
          <section aria-labelledby="payments-title" className="flex flex-col gap-3">
            <h2 id="payments-title" className="text-2xl font-bold">
              {text.lease.payments}
            </h2>
            {statement.data.statement.payments.length === 0 ? (
              <p>{text.lease.noPayments}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {[...statement.data.statement.payments].reverse().map((payment) => (
                  <PaymentRow key={payment.id} payment={payment} leaseId={leaseId} />
                ))}
              </ul>
            )}
          </section>
          <TenantLinkBlock leaseId={leaseId} />
          {lease && (
            <LeaseActions
              lease={lease}
              statement={statement.data.statement}
              onDone={(message) => {
                setNotice({ message, bankThreshold: null, beforeControl: false });
              }}
            />
          )}
        </>
      )}
      <Link to="/app/contratos" className={textLink}>
        {text.lease.back}
      </Link>
    </div>
  );
}
