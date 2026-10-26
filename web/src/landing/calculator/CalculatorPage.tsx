import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { formatDay } from "../dates";
import { copy as landingCopy } from "../copy";
import { formatSoles, parseSolesToCents } from "../money";
import { PublicFooter } from "../PublicFooter";
import { WaitlistForm } from "../WaitlistForm";
import { calculatorCopy as text } from "./copy";

type CalculatorResponse = components["schemas"]["CalculatorResponse"];
type RucGroup = NonNullable<components["schemas"]["CalculatorRequest"]["ruc_group"]>;
type Outcome =
  | { kind: "done"; year: string; result: CalculatorResponse; askedGroup: boolean }
  | { kind: "unknown_year"; year: string }
  | { kind: "limited"; year: string };

const FIRST_YEAR = 2026;
const MAX_RENTERS = 20;
const BASIS_POINTS = 10_000;
const RUC_DIGIT_GROUPS: Record<string, RucGroup> = {
  "0": "0",
  "1": "1",
  "2": "2-3",
  "3": "2-3",
  "4": "4-5",
  "5": "4-5",
  "6": "6-7",
  "7": "6-7",
  "8": "8-9",
  "9": "8-9",
  bc: "bc",
};

const limaMonth = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Lima",
  year: "numeric",
  month: "2-digit",
});

function currentLimaPeriod(): { year: number; month: number } {
  const [year = "", month = ""] = limaMonth.format(new Date()).split("-");
  return { year: Number(year), month: Number(month) };
}

const schema = z.object({
  year: z.string(),
  month: z.string(),
  ruc: z.string(),
  amounts: z.array(
    z.object({
      value: z
        .string()
        .refine((value) => parseSolesToCents(value) !== null, { error: text.errors.amount }),
    }),
  ),
});

type CalculatorValues = z.input<typeof schema>;

const HUNDREDTHS_OF_A_PERCENT = 10_000;

export function formatPercent(numerator: number, denominator: number): string {
  const hundredths = Math.round((numerator * HUNDREDTHS_OF_A_PERCENT) / denominator);
  const whole = Math.trunc(hundredths / 100);
  const rest = hundredths % 100;
  return rest === 0 ? String(whole) : `${String(whole)}.${String(rest).padStart(2, "0").replace(/0$/, "")}`;
}

async function calculate(values: CalculatorValues): Promise<Outcome> {
  const group = RUC_DIGIT_GROUPS[values.ruc];
  const { data, response } = await api.POST("/api/public/tax-calculator", {
    body: {
      period: `${values.year}-${values.month.padStart(2, "0")}`,
      collected_cents: values.amounts.map((amount) => parseSolesToCents(amount.value) ?? 0),
      ruc_group: group ?? null,
    },
  });
  if (data) {
    return { kind: "done", year: values.year, result: data, askedGroup: group !== undefined };
  }
  if (response.status === 404) {
    return { kind: "unknown_year", year: values.year };
  }
  if (response.status === 429) {
    return { kind: "limited", year: values.year };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function Result({ outcome }: { outcome: Outcome }) {
  if (outcome.kind === "unknown_year") {
    return <p role="alert">{text.errors.unknownYear(outcome.year)}</p>;
  }
  if (outcome.kind === "limited") {
    return <p role="alert">{text.errors.tooManyAttempts}</p>;
  }
  const { result, askedGroup } = outcome;
  const net = BASIS_POINTS - result.deduction_bp;
  return (
    <section aria-labelledby="calculator-result" className="flex flex-col gap-3" role="status">
      <h2 id="calculator-result" className="text-2xl font-bold">
        {text.result.title}
      </h2>
      <table className="w-full border-collapse text-left">
        <thead>
          <tr>
            <th className="border-b border-stone-300 py-2">{text.result.renter}</th>
            <th className="border-b border-stone-300 py-2">{text.result.collected}</th>
            <th className="border-b border-stone-300 py-2">{text.result.tax}</th>
          </tr>
        </thead>
        <tbody>
          {result.lines.map((line, index) => (
            <tr key={index}>
              <td className="py-2">{index + 1}</td>
              <td className="py-2">{formatSoles(line.collected_cents)}</td>
              <td className="py-2 font-semibold">{formatSoles(line.tax_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-lg font-bold">
        {text.result.total(formatSoles(result.total_tax_cents), result.lines.length)}
      </p>
      <p>
        {result.due_on
          ? text.result.dueOn(formatDay(result.due_on))
          : askedGroup
            ? text.result.noSchedule(outcome.year)
            : text.result.askRuc}
      </p>
      <p>
        {text.result.rate(
          formatPercent(result.rate_bp * net, BASIS_POINTS * BASIS_POINTS),
          formatPercent(result.rate_bp, BASIS_POINTS),
          formatPercent(net, BASIS_POINTS),
        )}
      </p>
      <p className="text-stone-600">{text.result.disclaimer}</p>
    </section>
  );
}

const inputClass = "min-h-11 rounded-lg border border-stone-400 px-3 text-base";

export function CalculatorPage() {
  const today = currentLimaPeriod();
  const years = Array.from({ length: today.year - FIRST_YEAR + 1 }, (_, i) => FIRST_YEAR + i);
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<CalculatorValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      year: String(today.year),
      month: String(today.month),
      ruc: "",
      amounts: [{ value: "" }],
    },
  });
  const { fields, append, remove } = useFieldArray({ control, name: "amounts" });
  const mutation = useMutation({ mutationFn: calculate });

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <Link to="/" className="text-brand underline">
        {landingCopy.privacyBack}
      </Link>
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-bold">{text.title}</h1>
        <p>{text.intro}</p>
      </header>

      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(event) => {
          void handleSubmit((values) => {
            mutation.mutate(values);
          })(event);
        }}
      >
        <div className="flex gap-3">
          <label className="flex flex-1 flex-col gap-1 font-medium">
            {text.month}
            <select className={inputClass} {...register("month")}>
              {text.months.map((name, index) => (
                <option key={name} value={String(index + 1)}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 font-medium">
            {text.year}
            <select className={inputClass} {...register("year")}>
              {years.map((year) => (
                <option key={year} value={String(year)}>
                  {year}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="flex flex-col gap-3">
          <legend className="mb-1 font-medium">{text.amountsTitle}</legend>
          {fields.map((field, index) => {
            const error = errors.amounts?.[index]?.value;
            const id = `amount-${String(index)}`;
            return (
              <div key={field.id} className="flex flex-col gap-1">
                <label htmlFor={id}>{text.renter(index + 1)}</label>
                <div className="flex gap-2">
                  <input
                    id={id}
                    inputMode="decimal"
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? `${id}-error` : undefined}
                    className={`${inputClass} flex-1`}
                    {...register(`amounts.${String(index)}.value` as `amounts.${number}.value`)}
                  />
                  {fields.length > 1 && (
                    <button
                      type="button"
                      aria-label={text.remove(index + 1)}
                      className="min-h-11 min-w-11 rounded-lg border border-stone-400"
                      onClick={() => {
                        remove(index);
                      }}
                    >
                      ×
                    </button>
                  )}
                </div>
                {error && (
                  <p id={`${id}-error`} className="text-red-800">
                    {error.message}
                  </p>
                )}
              </div>
            );
          })}
          {fields.length < MAX_RENTERS && (
            <button
              type="button"
              className="min-h-11 self-start rounded-lg border border-brand px-4 font-semibold text-brand"
              onClick={() => {
                append({ value: "" });
              }}
            >
              {text.add}
            </button>
          )}
        </fieldset>

        <label className="flex flex-col gap-1 font-medium">
          {text.rucGroup}
          <span className="font-normal text-stone-600">{text.rucGroupHint}</span>
          <select className={inputClass} {...register("ruc")}>
            <option value="">{text.rucGroupNone}</option>
            {["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"].map((digit) => (
              <option key={digit} value={digit}>
                {digit}
              </option>
            ))}
            <option value="bc">{text.goodTaxpayer}</option>
          </select>
        </label>

        <button
          type="submit"
          disabled={mutation.isPending}
          className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {mutation.isPending ? text.calculating : text.calculate}
        </button>
      </form>

      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {mutation.data && <Result outcome={mutation.data} />}

      <section aria-labelledby="calculator-waitlist" className="flex flex-col gap-4">
        <h2 id="calculator-waitlist" className="text-2xl font-bold">
          {text.waitlistTitle}
        </h2>
        <WaitlistForm source="calculator" />
      </section>

      <PublicFooter />
    </div>
  );
}
