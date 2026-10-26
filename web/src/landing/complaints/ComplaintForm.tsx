import { zodResolver } from "@hookform/resolvers/zod";
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import {
  useForm,
  useWatch,
  type FieldError,
  type UseFormRegisterReturn,
} from "react-hook-form";

import { complaintsCopy as text } from "./copy";
import { emptySheet, sheetSchema, type SheetValues } from "./sheet";

const inputClass = "min-h-11 rounded-lg border border-stone-400 px-3 text-base";

function TextField({
  id,
  label,
  hint,
  error,
  multiline = false,
  inputMode,
  autoComplete,
  registration,
}: {
  id: string;
  label: string;
  hint?: string;
  error: FieldError | undefined;
  multiline?: boolean;
  inputMode?: "text" | "email" | "tel" | "decimal";
  autoComplete?: string;
  registration: UseFormRegisterReturn;
}) {
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  const shared = {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy || undefined,
    ...registration,
  };
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-base font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-base text-stone-600">
          {hint}
        </p>
      )}
      {multiline ? (
        <textarea rows={5} className={`${inputClass} py-2`} {...shared} />
      ) : (
        <input
          type={inputMode === "email" ? "email" : inputMode === "tel" ? "tel" : "text"}
          inputMode={inputMode}
          autoComplete={autoComplete}
          className={inputClass}
          {...shared}
        />
      )}
      {error && (
        <p id={`${id}-error`} className="text-base text-red-800">
          {error.message}
        </p>
      )}
    </div>
  );
}

function Choice({
  legend,
  children,
}: {
  legend: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-base font-medium">{legend}</legend>
      {children}
    </fieldset>
  );
}

function Option({
  value,
  label,
  description,
  registration,
}: {
  value: string;
  label: string;
  description?: string;
  registration: UseFormRegisterReturn;
}) {
  return (
    <label className="flex min-h-11 items-start gap-3 text-base">
      <input type="radio" value={value} className="mt-1 size-6 shrink-0" {...registration} />
      <span>
        <span className="font-medium">{label}</span>
        {description && <span className="block text-stone-600">{description}</span>}
      </span>
    </label>
  );
}

export function ComplaintForm({ onReview }: { onReview: (values: SheetValues) => void }) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<SheetValues>({ resolver: zodResolver(sheetSchema), defaultValues: emptySheet });
  const isMinor = useWatch({ control, name: "isMinor" });

  return (
    <form
      noValidate
      className="flex flex-col gap-8"
      onSubmit={(event) => {
        void handleSubmit(onReview)(event);
      }}
    >
      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-bold">{text.consumer.title}</h2>
        <TextField
          id="full-name"
          label={text.consumer.fullName}
          autoComplete="name"
          error={errors.fullName}
          registration={register("fullName")}
        />
        <Choice legend={text.consumer.documentType}>
          {(["dni", "ce", "passport"] as const).map((type) => (
            <Option
              key={type}
              value={type}
              label={text.consumer.documentTypes[type]}
              registration={register("documentType")}
            />
          ))}
        </Choice>
        <TextField
          id="document-number"
          label={text.consumer.documentNumber}
          error={errors.documentNumber}
          registration={register("documentNumber")}
        />
        <TextField
          id="address"
          label={text.consumer.address}
          hint={text.consumer.addressHint}
          autoComplete="street-address"
          error={errors.address}
          registration={register("address")}
        />
        <TextField
          id="phone"
          label={text.consumer.phone}
          inputMode="tel"
          autoComplete="tel"
          error={errors.phone}
          registration={register("phone")}
        />
        <TextField
          id="email"
          label={text.consumer.email}
          hint={text.consumer.emailHint}
          inputMode="email"
          autoComplete="email"
          error={errors.email}
          registration={register("email")}
        />
        <label className="flex min-h-11 items-center gap-3 text-base">
          <input type="checkbox" className="size-6 shrink-0" {...register("isMinor")} />
          {text.consumer.isMinor}
        </label>
        {isMinor && (
          <div className="flex flex-col gap-4 border-l-4 border-stone-300 pl-4">
            <TextField
              id="guardian-name"
              label={text.consumer.guardianName}
              error={errors.guardianName}
              registration={register("guardianName")}
            />
            <TextField
              id="guardian-address"
              label={text.consumer.guardianAddress}
              error={errors.guardianAddress}
              registration={register("guardianAddress")}
            />
            <TextField
              id="guardian-phone"
              label={text.consumer.guardianPhone}
              inputMode="tel"
              error={errors.guardianPhone}
              registration={register("guardianPhone")}
            />
            <TextField
              id="guardian-email"
              label={text.consumer.guardianEmail}
              inputMode="email"
              error={errors.guardianEmail}
              registration={register("guardianEmail")}
            />
          </div>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-bold">{text.item.title}</h2>
        <Choice legend={text.item.kind}>
          {(["service", "product"] as const).map((kind) => (
            <Option
              key={kind}
              value={kind}
              label={text.item.kinds[kind]}
              registration={register("itemKind")}
            />
          ))}
        </Choice>
        <TextField
          id="claimed-amount"
          label={text.item.amount}
          hint={text.item.amountHint}
          inputMode="decimal"
          error={errors.claimedAmount}
          registration={register("claimedAmount")}
        />
        <TextField
          id="item-description"
          label={text.item.description}
          multiline
          error={errors.itemDescription}
          registration={register("itemDescription")}
        />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-bold">{text.claim.title}</h2>
        <Choice legend={text.claim.kind}>
          {(["claim", "complaint"] as const).map((kind) => (
            <Option
              key={kind}
              value={kind}
              label={text.claim.kinds[kind].label}
              description={text.claim.kinds[kind].definition}
              registration={register("kind")}
            />
          ))}
        </Choice>
        <TextField
          id="detail"
          label={text.claim.detail}
          hint={text.claim.detailHint}
          multiline
          error={errors.detail}
          registration={register("detail")}
        />
        <TextField
          id="request"
          label={text.claim.request}
          hint={text.claim.requestHint}
          multiline
          error={errors.request}
          registration={register("request")}
        />
      </section>

      <section className="flex flex-col gap-4">
        <Choice legend={text.channel.title}>
          {(["email", "letter"] as const).map((channel) => (
            <Option
              key={channel}
              value={channel}
              label={text.channel.options[channel]}
              registration={register("responseChannel")}
            />
          ))}
        </Choice>
      </section>

      <p className="text-base">
        {text.privacyNotice}{" "}
        <Link to="/privacidad" className="text-brand underline">
          {text.privacyLink}
        </Link>
        .
      </p>

      <button
        type="submit"
        className="min-h-11 rounded-lg bg-brand px-5 text-base font-semibold text-white hover:bg-brand-dark"
      >
        {text.toReview}
      </button>
    </form>
  );
}
