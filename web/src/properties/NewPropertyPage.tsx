import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";
import { useFieldArray, useForm } from "react-hook-form";

import { fetchProfile } from "../account/ProfilePage";
import { ErrorText, primaryButton, secondaryButton, textLink } from "../account/fields";
import { api } from "../api/client";
import { propertiesCopy as text } from "./copy";
import {
  PropertyFields,
  propertyBody,
  propertyDefaults,
  propertySchema,
  UNIT_KINDS,
  type PropertyValues,
} from "./PropertyFields";

const EMPTY_UNIT = { name: "", kind: "room" } as const;

async function createProperty(values: PropertyValues): Promise<void> {
  const { response } = await api.POST("/api/app/properties", {
    body: {
      ...propertyBody(values),
      units: values.units.map((unit) => ({ ...unit, name: unit.name.trim() })),
    },
  });
  if (response.status !== 201) {
    throw new Error(`Unexpected status ${String(response.status)}`);
  }
}

function NewPropertyForm({ estateAccount }: { estateAccount: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<PropertyValues>({
    resolver: zodResolver(propertySchema),
    defaultValues: propertyDefaults(estateAccount, [EMPTY_UNIT]),
  });
  const units = useFieldArray({ control, name: "units" });
  const mutation = useMutation({
    mutationFn: createProperty,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["properties"] });
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      await navigate({ to: "/app/inmuebles" });
    },
  });

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
      <PropertyFields
        estateAccount={estateAccount}
        register={register}
        control={control}
        errors={errors}
      />
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-1 text-base font-medium">{text.form.units}</legend>
        <p className="text-base text-stone-600">{text.form.unitsHint}</p>
        {units.fields.map((unit, index) => {
          const position = index + 1;
          const nameId = `unit-${String(index)}-name`;
          const kindId = `unit-${String(index)}-kind`;
          return (
            <div
              key={unit.id}
              className="flex flex-col gap-2 rounded-lg border border-stone-300 p-3"
            >
              <label htmlFor={nameId}>{text.form.unitName(position)}</label>
              <input
                id={nameId}
                className="min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base"
                aria-invalid={errors.units?.[index]?.name ? true : undefined}
                aria-describedby={errors.units?.[index]?.name ? `${nameId}-error` : undefined}
                {...register(`units.${String(index)}.name` as `units.${number}.name`)}
              />
              <ErrorText id={nameId} error={errors.units?.[index]?.name} />
              <label htmlFor={kindId}>{text.form.unitKind(position)}</label>
              <select
                id={kindId}
                className="min-h-11 w-full rounded-lg border border-stone-400 bg-white px-3 text-base"
                {...register(`units.${String(index)}.kind` as `units.${number}.kind`)}
              >
                {UNIT_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {text.unitKinds[kind]}
                  </option>
                ))}
              </select>
              {units.fields.length > 1 && (
                <button
                  type="button"
                  className="min-h-11 self-start text-brand underline"
                  onClick={() => {
                    units.remove(index);
                  }}
                >
                  {text.form.removeUnit(position)}
                </button>
              )}
            </div>
          );
        })}
        <button
          type="button"
          className={secondaryButton}
          onClick={() => {
            units.append(EMPTY_UNIT);
          }}
        >
          {text.form.addUnit}
        </button>
      </fieldset>
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      <button type="submit" disabled={mutation.isPending} className={primaryButton}>
        {mutation.isPending ? text.form.sending : text.form.submit}
      </button>
    </form>
  );
}

export function NewPropertyPage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: fetchProfile });

  if (profile.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.form.newTitle}</h1>
      {profile.data?.kind === "paused" && <p role="alert">{text.errors.paused}</p>}
      {profile.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {profile.data?.kind === "profile" && (
        <NewPropertyForm estateAccount={profile.data.profile.taxpayer_kind === "estate"} />
      )}
      <Link to="/app/inmuebles" className={textLink}>
        {text.form.cancel}
      </Link>
    </div>
  );
}
