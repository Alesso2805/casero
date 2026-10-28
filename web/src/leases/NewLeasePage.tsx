import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ErrorText, primaryButton, SelectField, TextField, textLink } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { parseSolesToCents } from "../landing/money";
import { fetchProperties } from "../properties/PropertiesPage";
import { leasesCopy as text } from "./copy";
import { fetchLeases, fetchRenters } from "./LeasesPage";
import { controlPeriods, FIRST_CONTROL_PERIOD, limaToday, periodLabel, uuidv7 } from "./terms";

type Property = components["schemas"]["PropertyResponse"];
type Renter = components["schemas"]["RenterResponse"];
type Lease = components["schemas"]["LeaseResponse"];

const TREATMENTS = ["standard", "company_tenant", "unsupported"] as const;
const DOC_TYPES = ["", "dni", "ce", "passport", "ruc"] as const;
const MAX_DUE_DAY = 31;

const optionalAmount = z
  .string()
  .trim()
  .refine((value) => value === "" || (parseSolesToCents(value) ?? 0) > 0, {
    error: text.errors.amount,
  });

const schema = z
  .object({
    unitId: z.string().min(1, text.errors.required),
    renterChoice: z.enum(["existing", "new"]),
    renterId: z.string(),
    renterName: z.string().trim().max(120),
    renterPhone: z.string().trim().max(30),
    docType: z.enum(DOC_TYPES),
    docNumber: z.string().trim().max(30),
    rent: z
      .string()
      .trim()
      .refine((value) => (parseSolesToCents(value) ?? 0) > 0, { error: text.errors.amount }),
    dueDay: z
      .string()
      .trim()
      .refine(
        (value) => /^\d{1,2}$/.test(value) && Number(value) >= 1 && Number(value) <= MAX_DUE_DAY,
        { error: text.errors.dueDay },
      ),
    startDate: z.string().min(1, text.errors.required),
    endDate: z.string(),
    controlFrom: z.string(),
    taxTreatment: z.enum(TREATMENTS),
    pre2026: optionalAmount,
    from2026: optionalAmount,
  })
  .superRefine((values, context) => {
    const missing = (path: string) => {
      context.addIssue({ code: "custom", path: [path], message: text.errors.required });
    };
    if (values.renterChoice === "existing" && values.renterId === "") {
      missing("renterId");
    }
    if (values.renterChoice === "new" && values.renterName.trim() === "") {
      missing("renterName");
    }
    if (values.renterChoice === "new" && values.docType !== "" && values.docNumber === "") {
      missing("docNumber");
    }
    if (values.endDate !== "" && values.endDate < values.startDate) {
      context.addIssue({ code: "custom", path: ["endDate"], message: text.errors.endBeforeStart });
    }
  });

type LeaseValues = z.input<typeof schema>;
type Field = keyof LeaseValues;
interface Refusal {
  field: Field | "form";
  message: string;
}
type Outcome = "saved" | Refusal;

const RENTER_ERRORS: Record<string, Refusal> = {
  duplicate_document: { field: "docNumber", message: text.errors.duplicateDocument },
  invalid_phone: { field: "renterPhone", message: text.errors.invalidPhone },
  invalid_document: { field: "docNumber", message: text.errors.invalidDocument },
};
const LEASE_ERRORS: Record<string, Refusal> = {
  plan_limit: { field: "form", message: text.errors.planLimit },
  unit_occupied: { field: "unitId", message: text.errors.unitOccupied },
  unit_archived: { field: "unitId", message: text.errors.unitArchived },
  control_period_out_of_range: { field: "controlFrom", message: text.errors.controlOutOfRange },
  balance_2026_without_months: { field: "from2026", message: text.errors.balance2026 },
  end_before_start: { field: "endDate", message: text.errors.endBeforeStart },
};

function detailOf(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : "";
}

function cents(value: string): number | null {
  return value.trim() === "" ? null : parseSolesToCents(value);
}

async function createRenter(values: LeaseValues): Promise<{ renterId: string } | Refusal> {
  const { data, error } = await api.POST("/api/app/renters", {
    body: {
      full_name: values.renterName.trim(),
      phone: values.renterPhone.trim() || null,
      document:
        values.docType === "" ? null : { doc_type: values.docType, number: values.docNumber },
    },
  });
  if (data) {
    return { renterId: data.id };
  }
  return RENTER_ERRORS[detailOf(error)] ?? { field: "form", message: text.errors.failure };
}

async function createLease(leaseId: string, renterId: string, values: LeaseValues): Promise<Outcome> {
  const { data, error } = await api.POST("/api/app/leases", {
    body: {
      id: leaseId,
      unit_id: values.unitId,
      renter_id: renterId,
      monthly_rent_cents: parseSolesToCents(values.rent) ?? 0,
      due_day: Number(values.dueDay),
      start_date: values.startDate,
      end_date: values.endDate || null,
      control_from_period: values.controlFrom,
      tax_treatment: values.taxTreatment,
      opening_balance_pre_2026_cents: values.startDate < "2026-01-01" ? cents(values.pre2026) : null,
      opening_balance_2026_cents:
        values.controlFrom > FIRST_CONTROL_PERIOD ? cents(values.from2026) : null,
    },
  });
  if (data) {
    return "saved";
  }
  return LEASE_ERRORS[detailOf(error)] ?? { field: "form", message: text.errors.failure };
}

function freeUnits(properties: Property[], leases: Lease[]) {
  const taken = new Set(leases.filter((lease) => lease.ended_at === null).map((lease) => lease.unit_id));
  return properties
    .filter((property) => !property.archived)
    .map((property) => ({
      property,
      units: property.units.filter((unit) => !unit.archived && !taken.has(unit.id)),
    }))
    .filter((group) => group.units.length > 0);
}

function NewLeaseForm({
  properties,
  renters,
  leases,
}: {
  properties: Property[];
  renters: Renter[];
  leases: Lease[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [leaseId] = useState(uuidv7);
  const today = limaToday();
  const groups = freeUnits(properties, leases);
  const {
    register,
    control,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<LeaseValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      unitId: "",
      renterChoice: renters.length > 0 ? "existing" : "new",
      renterId: "",
      renterName: "",
      renterPhone: "",
      docType: "",
      docNumber: "",
      rent: "",
      dueDay: "",
      startDate: today,
      endDate: "",
      controlFrom: today.slice(0, 7),
      taxTreatment: "standard",
      pre2026: "",
      from2026: "",
    },
  });
  const [unitId, renterChoice, docType, startDate, controlFrom] = useWatch({
    control,
    name: ["unitId", "renterChoice", "docType", "startDate", "controlFrom"],
  });
  const periods = controlPeriods(startDate, today);
  const latest = periods.at(-1) ?? today.slice(0, 7);
  const allowed = periods.includes(controlFrom);
  useEffect(() => {
    if (!allowed) {
      setValue("controlFrom", latest);
    }
  }, [allowed, latest, setValue]);
  const split = properties.some(
    (property) =>
      property.ownership === "conjugal_split" && property.units.some((unit) => unit.id === unitId),
  );

  const mutation = useMutation({
    mutationFn: async (values: LeaseValues): Promise<Outcome> => {
      let renterId = values.renterId;
      if (values.renterChoice === "new") {
        const created = await createRenter(values);
        if (!("renterId" in created)) {
          return created;
        }
        renterId = created.renterId;
        await queryClient.invalidateQueries({ queryKey: ["renters"] });
        setValue("renterChoice", "existing");
        setValue("renterId", renterId);
      }
      return createLease(leaseId, renterId, values);
    },
    onSuccess: async (outcome) => {
      if (outcome === "saved") {
        await queryClient.invalidateQueries({ queryKey: ["leases"] });
        await navigate({ to: "/app/contratos" });
      } else if (outcome.field !== "form") {
        setError(outcome.field, { message: outcome.message });
      }
    },
  });
  const outcome = mutation.data;
  let formError: string | null = mutation.isError ? text.errors.failure : null;
  if (outcome !== undefined && outcome !== "saved" && outcome.field === "form") {
    formError = outcome.message;
  }

  if (groups.length === 0) {
    return (
      <div className="flex flex-col gap-4">
        <p>{text.form.noUnits}</p>
        <Link to="/app/inmuebles/nuevo" className={textLink}>
          {text.form.addProperty}
        </Link>
      </div>
    );
  }
  return (
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          mutation.mutate(values);
        })(event);
      }}
    >
      <SelectField id="unit" label={text.form.unit} error={errors.unitId} registration={register("unitId")}>
        <option value="" />
        {groups.map(({ property, units }) => (
          <optgroup key={property.id} label={property.name}>
            {units.map((unit) => (
              <option key={unit.id} value={unit.id}>
                {unit.name}
              </option>
            ))}
          </optgroup>
        ))}
      </SelectField>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-base font-medium">{text.form.renter}</legend>
        {renters.length > 0 && (
          <>
            <label className="flex min-h-11 items-center gap-3">
              <input type="radio" value="existing" className="size-6" {...register("renterChoice")} />
              {text.form.existingRenter}
            </label>
            <label className="flex min-h-11 items-center gap-3">
              <input type="radio" value="new" className="size-6" {...register("renterChoice")} />
              {text.form.newRenter}
            </label>
          </>
        )}
        {renterChoice === "existing" ? (
          <SelectField
            id="renter"
            label={text.form.chooseRenter}
            error={errors.renterId}
            registration={register("renterId")}
          >
            <option value="" />
            {renters.map((renter) => (
              <option key={renter.id} value={renter.id}>
                {renter.full_name}
              </option>
            ))}
          </SelectField>
        ) : (
          <>
            <TextField
              id="renter-name"
              label={text.form.renterName}
              autoComplete="off"
              error={errors.renterName}
              registration={register("renterName")}
            />
            <TextField
              id="renter-phone"
              label={text.form.renterPhone}
              hint={text.form.renterPhoneHint}
              numeric
              autoComplete="off"
              error={errors.renterPhone}
              registration={register("renterPhone")}
            />
            <SelectField
              id="doc-type"
              label={text.form.docType}
              hint={text.form.docHint}
              error={errors.docType}
              registration={register("docType")}
            >
              {DOC_TYPES.map((type) => (
                <option key={type} value={type}>
                  {text.form.docTypes[type]}
                </option>
              ))}
            </SelectField>
            {docType !== "" && (
              <TextField
                id="doc-number"
                label={text.form.docNumber}
                autoComplete="off"
                error={errors.docNumber}
                registration={register("docNumber")}
              />
            )}
          </>
        )}
      </fieldset>

      <TextField
        id="rent"
        label={text.form.rent}
        hint={text.form.rentHint}
        decimal
        autoComplete="off"
        error={errors.rent}
        registration={register("rent")}
      />
      <TextField
        id="due-day"
        label={text.form.dueDay}
        hint={text.form.dueDayHint}
        numeric
        autoComplete="off"
        error={errors.dueDay}
        registration={register("dueDay")}
      />
      <TextField
        id="start-date"
        type="date"
        label={text.form.startDate}
        error={errors.startDate}
        registration={register("startDate")}
      />
      <TextField
        id="end-date"
        type="date"
        label={text.form.endDate}
        hint={text.form.endDateHint}
        error={errors.endDate}
        registration={register("endDate")}
      />
      {periods.length > 1 ? (
        <SelectField
          id="control-from"
          label={text.form.controlFrom}
          hint={text.form.controlFromHint}
          error={errors.controlFrom}
          registration={register("controlFrom")}
        >
          {periods.map((period) => (
            <option key={period} value={period}>
              {periodLabel(period)}
            </option>
          ))}
        </SelectField>
      ) : (
        <div className="flex flex-col gap-1">
          <p>{text.form.controlFixed(periodLabel(latest))}</p>
          <ErrorText id="control-from" error={errors.controlFrom} />
        </div>
      )}

      {split ? (
        <p className="rounded-lg bg-stone-100 p-4">{text.form.splitNotice}</p>
      ) : (
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-base font-medium">{text.form.taxTreatment}</legend>
          {TREATMENTS.map((treatment) => (
            <div key={treatment} className="flex flex-col gap-1">
              <label className="flex min-h-11 items-center gap-3">
                <input
                  type="radio"
                  value={treatment}
                  className="size-6 shrink-0"
                  aria-describedby={`treatment-${treatment}-hint`}
                  {...register("taxTreatment")}
                />
                {text.form.treatments[treatment].label}
              </label>
              <p id={`treatment-${treatment}-hint`} className="ml-9 text-base text-stone-600">
                {text.form.treatments[treatment].hint}
              </p>
            </div>
          ))}
        </fieldset>
      )}

      {startDate !== "" && startDate < "2026-01-01" && (
        <TextField
          id="pre-2026"
          label={text.form.pre2026}
          hint={text.form.pre2026Hint}
          decimal
          autoComplete="off"
          error={errors.pre2026}
          registration={register("pre2026")}
        />
      )}
      {controlFrom > FIRST_CONTROL_PERIOD && (
        <TextField
          id="from-2026"
          label={text.form.from2026}
          hint={text.form.from2026Hint}
          decimal
          autoComplete="off"
          error={errors.from2026}
          registration={register("from2026")}
        />
      )}

      {formError && (
        <p role="alert" className="text-red-800">
          {formError}
        </p>
      )}
      <button type="submit" disabled={mutation.isPending} className={primaryButton}>
        {mutation.isPending ? text.form.sending : text.form.submit}
      </button>
    </form>
  );
}

export function NewLeasePage() {
  const properties = useQuery({ queryKey: ["properties"], queryFn: fetchProperties });
  const renters = useQuery({ queryKey: ["renters"], queryFn: fetchRenters });
  const leases = useQuery({ queryKey: ["leases"], queryFn: fetchLeases });

  if (leases.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.form.title}</h1>
      {leases.data?.kind === "paused" && <p role="alert">{text.errors.paused}</p>}
      {(properties.isError || renters.isError || leases.isError) && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {properties.data?.kind === "properties" &&
        renters.data?.kind === "data" &&
        leases.data?.kind === "data" && (
          <NewLeaseForm
            properties={properties.data.properties}
            renters={renters.data.data}
            leases={leases.data.data}
          />
        )}
      <Link to="/app/contratos" className={textLink}>
        {text.form.cancel}
      </Link>
    </div>
  );
}
