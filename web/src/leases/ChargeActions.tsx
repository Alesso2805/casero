import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { primaryButton, secondaryButton } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { parseSolesToCents } from "../landing/money";
import { leasesCopy as text } from "./copy";
import { uuidv7 } from "./terms";

type ChargeLine = components["schemas"]["ChargeLineResponse"];
type Outcome = "done" | "conflict" | "login";

const CORRECTABLE = new Set<ChargeLine["kind"]>(["rent", "rent_correction"]);
const inputClass = "min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base";

function useLeaseWrite(leaseId: string, write: () => Promise<Outcome>, onDone?: () => void) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: write,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["statement", leaseId] }),
    onSuccess: (outcome) => {
      if (outcome === "login") {
        void navigate({ to: "/ingresar" });
      } else if (outcome === "done") {
        onDone?.();
      }
    },
  });
}

function outcomeOf(response: Response, saved: boolean): Outcome {
  if (saved) {
    return "done";
  }
  if (response.status === 401) {
    return "login";
  }
  if (response.status === 409) {
    return "conflict";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

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
  const close = () => {
    setMode("idle");
  };
  const voiding = useLeaseWrite(
    leaseId,
    async () => {
      const { data, response } = await api.POST("/api/app/charges/{charge_id}/void", {
        params: { path: { charge_id: charge.id } },
        body: { reason: reason.trim() },
      });
      return outcomeOf(response, data !== undefined);
    },
    close,
  );
  const cents = parseSolesToCents(amount) ?? 0;
  const correcting = useLeaseWrite(
    leaseId,
    async () => {
      const { data, response } = await api.POST(
        "/api/app/leases/{lease_id}/charges/corrections",
        {
          params: { path: { lease_id: leaseId } },
          body: { id: correctionId, corrects_charge_id: charge.id, amount_cents: cents },
        },
      );
      return outcomeOf(response, data !== undefined);
    },
    close,
  );
  const canCorrect = charge.voided && CORRECTABLE.has(charge.kind) && !corrected;
  if (!charge.voided && mode === "void") {
    const reasonId = `charge-void-${charge.id}`;
    return (
      <div className="flex flex-col gap-2">
        <label htmlFor={reasonId}>{text.charge.voidReason}</label>
        <input
          id={reasonId}
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
              voiding.mutate();
            }}
          >
            {text.charge.voidConfirm}
          </button>
          <button type="button" className={secondaryButton} onClick={close}>
            {text.charge.cancel}
          </button>
        </div>
        {voiding.isError && (
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
              correcting.mutate();
            }}
          >
            {text.charge.correctConfirm}
          </button>
          <button type="button" className={secondaryButton} onClick={close}>
            {text.charge.cancel}
          </button>
        </div>
        {(correcting.isError || correcting.data === "conflict") && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
      </div>
    );
  }
  if (!charge.voided) {
    return (
      <button
        type="button"
        className={`${secondaryButton} self-start`}
        aria-label={text.charge.voidOf(label)}
        onClick={() => {
          setMode("void");
        }}
      >
        {text.charge.void}
      </button>
    );
  }
  if (canCorrect) {
    return (
      <button
        type="button"
        className={`${secondaryButton} self-start`}
        aria-label={text.charge.correctOf(label)}
        onClick={() => {
          setMode("correct");
        }}
      >
        {text.charge.correct}
      </button>
    );
  }
  return null;
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
  const saving = useLeaseWrite(leaseId, async () => {
    const { data, response } = await api.POST("/api/app/leases/{lease_id}/charges/adjustments", {
      params: { path: { lease_id: leaseId } },
      body: { id: adjustmentId, amount_cents: kind === "credit" ? -cents : cents },
    });
    return outcomeOf(response, data !== undefined);
  });
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
            if (outcome === "done") {
              onSaved();
            } else if (outcome === "conflict") {
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
