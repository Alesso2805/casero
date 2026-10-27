import type { Control, FieldErrors, UseFormRegister } from "react-hook-form";
import { useWatch } from "react-hook-form";
import { z } from "zod";

import { ErrorText, TextField } from "../account/fields";
import type { components } from "../api/schema";
import { parseSolesToCents } from "../landing/money";
import { propertiesCopy as text } from "./copy";

export type Ownership = components["schemas"]["PropertyResponse"]["ownership"];
export type PropertyBody = components["schemas"]["PropertyRequest"];

const PERSON_OWNERSHIPS = ["sole", "co_owned", "conjugal_option", "conjugal_split"] as const;
export const UNIT_KINDS = [
  "room",
  "mini_apartment",
  "apartment",
  "shop",
  "parking",
  "other",
] as const;
const MAX_SHARE = 100;

export const unitSchema = z.object({
  name: z.string().trim().min(1, text.errors.required).max(80),
  kind: z.enum(UNIT_KINDS),
});

export const propertyFields = {
  name: z.string().trim().min(1, text.errors.required).max(120),
  addressLine: z.string().trim().max(200),
  district: z.string().trim().max(80),
  ownership: z.enum([...PERSON_OWNERSHIPS, "estate"]),
  conjugalConfirmed: z.boolean(),
  autovaluo: z
    .string()
    .trim()
    .refine((value) => value === "" || (parseSolesToCents(value) ?? 0) > 0, {
      error: text.errors.autovaluo,
    }),
  rentedShare: z
    .string()
    .trim()
    .refine(
      (value) => /^\d{1,3}$/.test(value) && Number(value) >= 1 && Number(value) <= MAX_SHARE,
      { error: text.errors.rentedShare },
    ),
  units: z.array(unitSchema),
};

export const propertySchema = z.object(propertyFields).superRefine(requireConjugalConfirmation);

export type PropertyValues = z.input<typeof propertySchema>;

export function requireConjugalConfirmation(
  values: Pick<PropertyValues, "ownership" | "conjugalConfirmed">,
  context: z.RefinementCtx,
) {
  if (values.ownership === "conjugal_option" && !values.conjugalConfirmed) {
    context.addIssue({
      code: "custom",
      path: ["conjugalConfirmed"],
      message: text.errors.conjugalConfirmation,
    });
  }
}

export function propertyDefaults(
  estateAccount: boolean,
  units: PropertyValues["units"],
): PropertyValues {
  return {
    name: "",
    addressLine: "",
    district: "",
    ownership: estateAccount ? "estate" : "sole",
    conjugalConfirmed: false,
    autovaluo: "",
    rentedShare: String(MAX_SHARE),
    units,
  };
}

export function propertyBody(values: PropertyValues): PropertyBody {
  const autovaluo = values.autovaluo.trim();
  return {
    name: values.name.trim(),
    address_line: values.addressLine.trim() || null,
    district: values.district.trim() || null,
    ownership: values.ownership,
    conjugal_option_confirmed: values.ownership === "conjugal_option" && values.conjugalConfirmed,
    autovaluo_cents: autovaluo === "" ? null : parseSolesToCents(autovaluo),
    rented_share_pct: Number(values.rentedShare),
  };
}

interface FieldsProps {
  estateAccount: boolean;
  register: UseFormRegister<PropertyValues>;
  control: Control<PropertyValues>;
  errors: FieldErrors<PropertyValues>;
}

export function PropertyFields({ estateAccount, register, control, errors }: FieldsProps) {
  const ownership = useWatch({ control, name: "ownership" });
  return (
    <>
      <TextField
        id="property-name"
        label={text.form.name}
        hint={text.form.nameHint}
        error={errors.name}
        registration={register("name")}
      />
      <TextField
        id="property-address"
        label={text.form.addressLine}
        autoComplete="street-address"
        error={errors.addressLine}
        registration={register("addressLine")}
      />
      <TextField
        id="property-district"
        label={text.form.district}
        error={errors.district}
        registration={register("district")}
      />
      {estateAccount ? (
        <p className="rounded-lg bg-stone-100 p-4">{text.form.ownerships.estate.hint}</p>
      ) : (
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-base font-medium">{text.form.ownership}</legend>
          {PERSON_OWNERSHIPS.map((option) => (
            <div key={option} className="flex flex-col gap-1">
              <label className="flex min-h-11 items-center gap-3">
                <input
                  type="radio"
                  value={option}
                  className="size-6 shrink-0"
                  aria-describedby={`ownership-${option}-hint`}
                  {...register("ownership")}
                />
                {text.form.ownerships[option].label}
              </label>
              <p id={`ownership-${option}-hint`} className="ml-9 text-base text-stone-600">
                {text.form.ownerships[option].hint}
              </p>
            </div>
          ))}
          {ownership === "conjugal_option" && (
            <div className="flex flex-col gap-1">
              <div className="flex items-start gap-3">
                <input
                  id="conjugal-confirmed"
                  type="checkbox"
                  className="mt-1 size-6 shrink-0"
                  aria-invalid={errors.conjugalConfirmed ? true : undefined}
                  aria-describedby={
                    errors.conjugalConfirmed ? "conjugal-confirmed-error" : undefined
                  }
                  {...register("conjugalConfirmed")}
                />
                <label htmlFor="conjugal-confirmed">{text.form.conjugalConfirmation}</label>
              </div>
              <ErrorText id="conjugal-confirmed" error={errors.conjugalConfirmed} />
            </div>
          )}
        </fieldset>
      )}
      <TextField
        id="property-autovaluo"
        label={text.form.autovaluo}
        hint={text.form.autovaluoHint}
        numeric
        error={errors.autovaluo}
        registration={register("autovaluo")}
      />
      <TextField
        id="property-share"
        label={text.form.rentedShare}
        hint={text.form.rentedShareHint}
        numeric
        error={errors.rentedShare}
        registration={register("rentedShare")}
      />
    </>
  );
}
