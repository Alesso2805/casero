import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { primaryButton, SelectField, TextField } from "../account/fields";
import { parseSolesToCents } from "../landing/money";
import { limaToday, uuidv7 } from "../leases/terms";
import { adminApi } from "./api";
import { adminCopy as text } from "./copy";

const MAX_MONTHS = 24;
const copy = text.paymentForm;

const schema = z.object({
  amount: z.string().refine((value) => (parseSolesToCents(value) ?? 0) > 0, copy.amountError),
  paid_on: z.string().min(1, text.required),
  method: z.enum(["yape", "transfer"]),
  boleta_number: z.string().trim().min(1, text.required).max(40),
  months: z.string().refine((value) => {
    const months = Number(value);
    return Number.isInteger(months) && months >= 1 && months <= MAX_MONTHS;
  }, copy.monthsError),
});

type PaymentValues = z.input<typeof schema>;
type Outcome = "recorded" | "future_date" | "closing" | "conflict";

const OUTCOME_ERRORS: Partial<Record<Outcome, string>> = {
  future_date: copy.futureDate,
  closing: copy.closing,
  conflict: copy.conflict,
};

async function recordPayment(
  accountId: string,
  id: string,
  values: PaymentValues,
): Promise<Outcome> {
  const { response, error } = await adminApi.POST("/api/admin/accounts/{account_id}/payments", {
    params: { path: { account_id: accountId } },
    body: {
      id,
      amount_cents: parseSolesToCents(values.amount) ?? 0,
      paid_on: values.paid_on,
      method: values.method,
      boleta_number: values.boleta_number,
      months: Number(values.months),
    },
  });
  if (response.status === 204) {
    return "recorded";
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (response.status === 422 && detail === "future_date") {
    return "future_date";
  }
  if (response.status === 409) {
    return detail === "account_closing" ? "closing" : "conflict";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function PaymentForm({ accountId }: { accountId: string }) {
  const queryClient = useQueryClient();
  // Generated once per payment, so sending the same one twice extends the plan once (rule 5).
  const [paymentId, setPaymentId] = useState(() => uuidv7());
  const defaults: PaymentValues = {
    amount: "",
    paid_on: limaToday(),
    method: "yape",
    boleta_number: "",
    months: "1",
  };
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PaymentValues>({ resolver: zodResolver(schema), defaultValues: defaults });
  const mutation = useMutation({
    mutationFn: (values: PaymentValues) => recordPayment(accountId, paymentId, values),
    onSuccess: async (outcome) => {
      if (outcome === "recorded") {
        setPaymentId(uuidv7());
        reset(defaults);
        await queryClient.invalidateQueries({ queryKey: ["account", accountId] });
      }
    },
  });
  const refused = mutation.data ? OUTCOME_ERRORS[mutation.data] : undefined;

  return (
    <section aria-labelledby="payment-title" className="flex max-w-md flex-col gap-4">
      <h2 id="payment-title" className="text-2xl font-bold">
        {copy.title}
      </h2>
      <p>{copy.rule}</p>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          void handleSubmit((values) => {
            mutation.mutate(values);
          })(event);
        }}
      >
        <TextField
          id="amount"
          label={copy.amount}
          decimal
          error={errors.amount}
          registration={register("amount")}
        />
        <TextField
          id="paid_on"
          label={copy.paidOn}
          type="date"
          error={errors.paid_on}
          registration={register("paid_on")}
        />
        <SelectField
          id="method"
          label={copy.method}
          error={errors.method}
          registration={register("method")}
        >
          <option value="yape">{copy.yape}</option>
          <option value="transfer">{copy.transfer}</option>
        </SelectField>
        <TextField
          id="boleta_number"
          label={copy.boleta}
          error={errors.boleta_number}
          registration={register("boleta_number")}
        />
        <TextField
          id="months"
          label={copy.months}
          numeric
          error={errors.months}
          registration={register("months")}
        />
        {refused && (
          <p role="alert" className="text-red-800">
            {refused}
          </p>
        )}
        {mutation.isError && (
          <p role="alert" className="text-red-800">
            {text.failure}
          </p>
        )}
        {mutation.data === "recorded" && <p role="status">{copy.recorded}</p>}
        <button type="submit" disabled={mutation.isPending} className={primaryButton}>
          {copy.submit}
        </button>
      </form>
    </section>
  );
}
