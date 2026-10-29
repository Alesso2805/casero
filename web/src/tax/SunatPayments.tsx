import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { primaryButton, secondaryButton, TextField } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles, parseSolesToCents, solesInput } from "../landing/money";
import { limaToday, uuidv7 } from "../leases/terms";
import { taxCopy } from "./copy";

const text = taxCopy.sunat;

type Declaration = components["schemas"]["DeclarationResponse"];
type DeclaredPayment = components["schemas"]["DeclaredPaymentResponse"];

const recordSchema = z.object({
  declaredBase: z
    .string()
    .trim()
    .refine((value) => parseSolesToCents(value) !== null, { error: text.errors.declaredBase }),
  amount: z
    .string()
    .trim()
    .refine((value) => (parseSolesToCents(value) ?? 0) > 0, { error: text.errors.amount }),
  paidOn: z.string().min(1, text.errors.paidOn),
  orderNumber: z.string().trim().regex(/^[0-9]{1,20}$/, text.errors.order),
});

type RecordValues = z.input<typeof recordSchema>;
type Outcome = "saved" | "conflict" | { field: "paidOn" | "form"; message: string };

const DATE_ERRORS: Record<string, string> = {
  paid_before_period: text.errors.paid_before_period,
  paid_in_future: text.errors.paid_in_future,
};

async function recordPayment(
  id: string,
  period: string,
  renterId: string,
  values: RecordValues,
): Promise<Outcome> {
  const { data, error, response } = await api.POST("/api/app/tax/payments", {
    body: {
      id,
      period,
      renter_id: renterId,
      declared_base_cents: parseSolesToCents(values.declaredBase) ?? 0,
      amount_cents: parseSolesToCents(values.amount) ?? 0,
      paid_on: values.paidOn,
      order_number: values.orderNumber.trim(),
    },
  });
  if (data) {
    return "saved";
  }
  if (response.status === 409) {
    return "conflict";
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  const dateError = typeof detail === "string" ? DATE_ERRORS[detail] : undefined;
  return dateError
    ? { field: "paidOn", message: dateError }
    : { field: "form", message: text.errors.failure };
}

function RecordForm({
  declaration,
  period,
  paymentId,
  onDone,
  onConflict,
}: {
  declaration: Declaration;
  period: string;
  paymentId: string;
  onDone: (saved: boolean) => void;
  onConflict: () => void;
}) {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const id = `sunat-${declaration.renter_id}`;
  const {
    register,
    handleSubmit,
    setError,
    setFocus,
    formState: { errors },
  } = useForm<RecordValues>({
    resolver: zodResolver(recordSchema),
    defaultValues: {
      declaredBase: solesInput(declaration.base_cents),
      amount: declaration.pending_cents > 0 ? solesInput(declaration.pending_cents) : "",
      paidOn: limaToday(),
      orderNumber: "",
    },
  });
  useEffect(() => {
    setFocus("amount");
  }, [setFocus]);
  const save = useMutation({
    mutationFn: (values: RecordValues) =>
      recordPayment(paymentId, period, declaration.renter_id, values),
    // A lost response may hide a saved payment, so the cards reload whatever happened.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["declarations"] }),
    onSuccess: (outcome) => {
      if (outcome === "saved") {
        onDone(true);
      } else if (outcome === "conflict") {
        setFormError(text.errors.conflict);
        onConflict();
      } else if (outcome.field === "paidOn") {
        setError("paidOn", { message: outcome.message });
      } else {
        setFormError(outcome.message);
      }
    },
  });
  return (
    <form
      noValidate
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        setFormError(null);
        void handleSubmit((values) => {
          save.mutate(values);
        })(event);
      }}
    >
      <TextField
        id={`${id}-base`}
        label={text.declaredBase}
        hint={text.declaredBaseHint}
        decimal
        error={errors.declaredBase}
        registration={register("declaredBase")}
      />
      <TextField
        id={`${id}-amount`}
        label={text.amount}
        decimal
        error={errors.amount}
        registration={register("amount")}
      />
      <TextField
        id={`${id}-paid-on`}
        label={text.paidOn}
        type="date"
        error={errors.paidOn}
        registration={register("paidOn")}
      />
      <TextField
        id={`${id}-order`}
        label={text.orderNumber}
        hint={text.orderHint}
        numeric
        autoComplete="off"
        error={errors.orderNumber}
        registration={register("orderNumber")}
      />
      <button type="submit" className={primaryButton} disabled={save.isPending}>
        {save.isPending ? text.saving : text.save}
      </button>
      <button
        type="button"
        className={secondaryButton}
        onClick={() => {
          onDone(false);
        }}
      >
        {text.cancel}
      </button>
      {formError && (
        <p role="alert" className="text-red-800">
          {formError}
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
    </form>
  );
}

function PaidLine({ payment, onVoided }: { payment: DeclaredPayment; onVoided: () => void }) {
  const queryClient = useQueryClient();
  const [voiding, setVoiding] = useState(false);
  const [reason, setReason] = useState("");
  const [missingReason, setMissingReason] = useState(false);
  const reasonInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (voiding) {
      reasonInput.current?.focus();
    }
  }, [voiding]);
  const amount = formatSoles(payment.amount_cents);
  const reasonId = `void-${payment.id}`;
  const voidPayment = useMutation({
    mutationFn: async () => {
      const { data } = await api.POST("/api/app/tax/payments/{payment_id}/void", {
        params: { path: { payment_id: payment.id } },
        body: { reason: reason.trim() },
      });
      if (!data) {
        throw new Error("Tax payment not voided");
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["declarations"] }),
    onSuccess: onVoided,
  });
  return (
    <li className="flex flex-col gap-2">
      <p>{text.paid(amount, formatDay(payment.paid_on), payment.order_number)}</p>
      {voiding ? (
        <div className="flex flex-col gap-2">
          <label htmlFor={reasonId} className="font-medium">
            {text.reason}
          </label>
          <input
            id={reasonId}
            ref={reasonInput}
            className="min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base"
            value={reason}
            maxLength={200}
            aria-invalid={missingReason ? true : undefined}
            aria-describedby={missingReason ? `${reasonId}-error` : undefined}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
          {missingReason && (
            <p id={`${reasonId}-error`} className="text-red-800">
              {text.errors.reason}
            </p>
          )}
          <button
            type="button"
            className={primaryButton}
            disabled={voidPayment.isPending}
            onClick={() => {
              setMissingReason(reason.trim() === "");
              if (reason.trim() !== "") {
                voidPayment.mutate();
              }
            }}
          >
            {text.confirmVoid}
          </button>
          <button
            type="button"
            className={secondaryButton}
            onClick={() => {
              setVoiding(false);
            }}
          >
            {text.cancel}
          </button>
          {voidPayment.isError && (
            <p role="alert" className="text-red-800">
              {text.errors.failure}
            </p>
          )}
        </div>
      ) : (
        <button
          type="button"
          className={secondaryButton}
          aria-label={text.voidLabel(amount)}
          onClick={() => {
            setVoiding(true);
          }}
        >
          {text.void}
        </button>
      )}
    </li>
  );
}

export function SunatPayments({ declaration, period }: { declaration: Declaration; period: string }) {
  const [draftId, setDraftId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const titleId = `sunat-title-${declaration.renter_id}`;
  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-2 border-t border-stone-200 pt-3">
      <h4 id={titleId} className="text-lg font-semibold">
        {text.title}
      </h4>
      {declaration.payments.length > 0 && (
        <ul className="flex flex-col gap-3">
          {declaration.payments.map((payment) => (
            <PaidLine
              key={payment.id}
              payment={payment}
              onVoided={() => {
                setNotice(text.voided);
              }}
            />
          ))}
        </ul>
      )}
      {declaration.pending_cents > 0 ? (
        <p className="font-semibold">{text.pending(formatSoles(declaration.pending_cents))}</p>
      ) : (
        declaration.paid_cents > 0 && <p className="font-semibold">{text.fullyPaid}</p>
      )}
      {draftId === null ? (
        <button
          type="button"
          className={secondaryButton}
          onClick={() => {
            setNotice(null);
            setDraftId(uuidv7());
          }}
        >
          {text.record}
        </button>
      ) : (
        <RecordForm
          declaration={declaration}
          period={period}
          paymentId={draftId}
          onDone={(saved) => {
            setDraftId(null);
            setNotice(saved ? text.saved : null);
          }}
          onConflict={() => {
            setDraftId(uuidv7());
          }}
        />
      )}
      <p role="status">{notice}</p>
    </section>
  );
}
