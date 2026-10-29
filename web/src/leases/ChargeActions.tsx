import { useEffect, useRef, useState } from "react";

import { primaryButton, secondaryButton } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { parseSolesToCents } from "../landing/money";
import { leasesCopy as text } from "./copy";
import { uuidv7 } from "./terms";
import { SunatVoidNotice } from "./SunatVoidNotice";
import { inputClass, type Outcome, outcomeOf, useLeaseWrite } from "./writes";

type ChargeLine = components["schemas"]["ChargeLineResponse"];

const CORRECTABLE = new Set<ChargeLine["kind"]>(["rent", "rent_correction"]);

export function ChargeActions({
  charge,
  label,
  leaseId,
  corrected,
}: {
  charge: ChargeLine;
  label: string;
  leaseId: string;
  corrected: boolean;
}) {
  const [mode, setMode] = useState<"idle" | "void" | "correct">("idle");
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [correctionId] = useState(uuidv7);
  const [paidToSunat, setPaidToSunat] = useState<string[]>([]);
  const cents = parseSolesToCents(amount) ?? 0;
  const voiding = useLeaseWrite(leaseId, async () => {
    const result = await api.POST("/api/app/charges/{charge_id}/void", {
      params: { path: { charge_id: charge.id } },
      body: { reason: reason.trim() },
    });
    setPaidToSunat(result.data?.paid_to_sunat ?? []);
    return outcomeOf(Promise.resolve(result));
  });
  const correcting = useLeaseWrite(leaseId, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/charges/corrections", {
        params: { path: { lease_id: leaseId } },
        body: { id: correctionId, corrects_charge_id: charge.id, amount_cents: cents },
      }),
    ),
  );
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (mode !== "idle") {
      field.current?.focus();
    }
  }, [mode]);
  // A refusal keeps the form open with its message; only a saved write closes it.
  const close = {
    onSuccess: (outcome: Outcome) => {
      if (outcome.kind === "done") {
        setMode("idle");
      }
    },
  };
  const canCorrect = charge.voided && CORRECTABLE.has(charge.kind) && !corrected;
  if (!charge.voided && mode === "void") {
    const reasonId = `charge-void-${charge.id}`;
    return (
      <div className="flex flex-col gap-2">
        <label htmlFor={reasonId}>{text.charge.voidReason}</label>
        <input
          id={reasonId}
          ref={field}
          className={inputClass}
          maxLength={200}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
          }}
        />
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className={primaryButton}
            disabled={reason.trim() === "" || voiding.isPending}
            onClick={() => {
              voiding.mutate(undefined, close);
            }}
          >
            {text.charge.voidConfirm}
          </button>
          <button
            type="button"
            className={secondaryButton}
            onClick={() => {
              setMode("idle");
            }}
          >
            {text.charge.cancel}
          </button>
        </div>
        {(voiding.isError || (voiding.data && voiding.data.kind !== "done")) && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
      </div>
    );
  }
  if (canCorrect && mode === "correct") {
    const amountId = `charge-correct-${charge.id}`;
    return (
      <div className="flex flex-col gap-2">
        <label htmlFor={amountId}>{text.charge.correctAmount}</label>
        <input
          id={amountId}
          ref={field}
          inputMode="decimal"
          className={inputClass}
          value={amount}
          onChange={(event) => {
            setAmount(event.target.value);
          }}
        />
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            className={primaryButton}
            disabled={cents <= 0 || correcting.isPending}
            onClick={() => {
              correcting.mutate(undefined, close);
            }}
          >
            {text.charge.correctConfirm}
          </button>
          <button
            type="button"
            className={secondaryButton}
            onClick={() => {
              setMode("idle");
            }}
          >
            {text.charge.cancel}
          </button>
        </div>
        {(correcting.isError || (correcting.data && correcting.data.kind !== "done")) && (
          <p role="alert" className="text-red-800">
            {correcting.data?.kind === "refused" && correcting.data.detail === "already_corrected"
              ? text.errors.alreadyCorrected
              : text.errors.failure}
          </p>
        )}
      </div>
    );
  }
  const notice = <SunatVoidNotice periods={paidToSunat} />;
  if (!charge.voided || canCorrect) {
    return (
      <>
        {notice}
        <button
          type="button"
          className={`${secondaryButton} self-start`}
          aria-label={charge.voided ? text.charge.correctOf(label) : text.charge.voidOf(label)}
          onClick={() => {
            setMode(charge.voided ? "correct" : "void");
          }}
        >
          {charge.voided ? text.charge.correct : text.charge.void}
        </button>
      </>
    );
  }
  return notice;
}

export function AdjustmentForm({
  leaseId,
  adjustmentId,
  onSaved,
  onConflict,
  onCancel,
}: {
  leaseId: string;
  adjustmentId: string;
  onSaved: () => void;
  onConflict: () => void;
  onCancel: () => void;
}) {
  const [kind, setKind] = useState<"debit" | "credit">("debit");
  const [amount, setAmount] = useState("");
  const [conflict, setConflict] = useState(false);
  const amountInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    amountInput.current?.focus();
  }, []);
  const cents = parseSolesToCents(amount) ?? 0;
  const saving = useLeaseWrite(leaseId, () =>
    outcomeOf(
      api.POST("/api/app/leases/{lease_id}/charges/adjustments", {
        params: { path: { lease_id: leaseId } },
        body: { id: adjustmentId, amount_cents: kind === "credit" ? -cents : cents },
      }),
    ),
  );
  return (
    <form
      noValidate
      aria-labelledby="adjustment-title"
      className="flex flex-col gap-4 rounded-lg border border-stone-300 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        setConflict(false);
        saving.mutate(undefined, {
          onSuccess: (outcome) => {
            if (outcome.kind === "done") {
              onSaved();
            } else if (outcome.kind === "conflict") {
              setConflict(true);
              onConflict();
            }
          },
        });
      }}
    >
      <h2 id="adjustment-title" className="text-2xl font-bold">
        {text.adjustment.title}
      </h2>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 font-medium">{text.adjustment.kind}</legend>
        {(["debit", "credit"] as const).map((option) => (
          <label key={option} className="flex min-h-11 items-center gap-3">
            <input
              type="radio"
              name="adjustment-kind"
              className="h-5 w-5"
              checked={kind === option}
              onChange={() => {
                setKind(option);
              }}
            />
            {text.adjustment[option]}
          </label>
        ))}
      </fieldset>
      <div className="flex flex-col gap-1">
        <label htmlFor="adjustment-amount" className="font-medium">
          {text.adjustment.amount}
        </label>
        <p id="adjustment-hint" className="text-stone-600">
          {text.adjustment.hint}
        </p>
        <input
          id="adjustment-amount"
          ref={amountInput}
          inputMode="decimal"
          aria-describedby="adjustment-hint"
          className={inputClass}
          value={amount}
          onChange={(event) => {
            setAmount(event.target.value);
          }}
        />
      </div>
      {saving.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {conflict && (
        <p role="alert" className="text-red-800">
          {text.adjustment.conflict}
        </p>
      )}
      <button type="submit" disabled={cents <= 0 || saving.isPending} className={primaryButton}>
        {text.adjustment.submit}
      </button>
      <button type="button" className={secondaryButton} onClick={onCancel}>
        {text.charge.cancel}
      </button>
    </form>
  );
}
