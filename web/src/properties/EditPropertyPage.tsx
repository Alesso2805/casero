import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";
import { useForm, type FieldErrors, type UseFormRegister } from "react-hook-form";
import type { z } from "zod";

import { fetchProfile } from "../account/ProfilePage";
import { ErrorText, primaryButton, secondaryButton, textLink } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { propertiesCopy as text } from "./copy";
import { fetchProperties } from "./PropertiesPage";
import {
  PropertyFields,
  propertyBody,
  propertySchema,
  propertyValues,
  UNIT_KINDS,
  unitSchema,
  type Property,
  type PropertyValues,
} from "./PropertyFields";

type Unit = components["schemas"]["UnitResponse"];
type UnitValues = z.input<typeof unitSchema>;
type Archived = "archived" | "active_lease";

const inputClass = "min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base";

function expectStatus(response: Response, expected: number) {
  if (response.status !== expected) {
    throw new Error(`Unexpected status ${String(response.status)}`);
  }
}

function archiveOutcome(response: Response): Archived {
  if (response.status === 409) {
    return "active_lease";
  }
  expectStatus(response, 200);
  return "archived";
}

function useRefreshProperties() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["properties"] });
}

function UnitInputs({
  idPrefix,
  register,
  errors,
}: {
  idPrefix: string;
  register: UseFormRegister<UnitValues>;
  errors: FieldErrors<UnitValues>;
}) {
  return (
    <>
      <label htmlFor={`${idPrefix}-name`}>{text.edit.unitName}</label>
      <input
        id={`${idPrefix}-name`}
        className={inputClass}
        aria-invalid={errors.name ? true : undefined}
        aria-describedby={errors.name ? `${idPrefix}-name-error` : undefined}
        {...register("name")}
      />
      <ErrorText id={`${idPrefix}-name`} error={errors.name} />
      <label htmlFor={`${idPrefix}-kind`}>{text.edit.unitKind}</label>
      <select id={`${idPrefix}-kind`} className={`${inputClass} bg-white`} {...register("kind")}>
        {UNIT_KINDS.map((kind) => (
          <option key={kind} value={kind}>
            {text.unitKinds[kind]}
          </option>
        ))}
      </select>
    </>
  );
}

function DetailsForm({ property, estateAccount }: { property: Property; estateAccount: boolean }) {
  const refresh = useRefreshProperties();
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<PropertyValues>({
    resolver: zodResolver(propertySchema),
    defaultValues: propertyValues(property),
  });
  const mutation = useMutation({
    mutationFn: async (values: PropertyValues) => {
      const { response } = await api.PUT("/api/app/properties/{property_id}", {
        params: { path: { property_id: property.id } },
        body: propertyBody(values),
      });
      expectStatus(response, 200);
    },
    onSuccess: refresh,
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
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {mutation.isSuccess && (
        <p role="status" className="text-green-800">
          {text.edit.saved}
        </p>
      )}
      <button type="submit" disabled={mutation.isPending} className={primaryButton}>
        {mutation.isPending ? text.form.sending : text.form.submit}
      </button>
    </form>
  );
}

function UnitEditor({ unit, onDone }: { unit: Unit; onDone: () => void }) {
  const refresh = useRefreshProperties();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<UnitValues>({
    resolver: zodResolver(unitSchema),
    defaultValues: { name: unit.name, kind: unit.kind },
  });
  const mutation = useMutation({
    mutationFn: async (values: UnitValues) => {
      const { response } = await api.PUT("/api/app/units/{unit_id}", {
        params: { path: { unit_id: unit.id } },
        body: { name: values.name.trim(), kind: values.kind },
      });
      expectStatus(response, 200);
    },
    onSuccess: async () => {
      await refresh();
      onDone();
    },
  });
  return (
    <form
      noValidate
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          mutation.mutate(values);
        })(event);
      }}
    >
      <UnitInputs idPrefix={`unit-${unit.id}`} register={register} errors={errors} />
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      <div className="flex gap-3">
        <button type="submit" disabled={mutation.isPending} className={primaryButton}>
          {text.edit.saveUnit}
        </button>
        <button type="button" className={secondaryButton} onClick={onDone}>
          {text.edit.cancel}
        </button>
      </div>
    </form>
  );
}

function UnitRow({ unit }: { unit: Unit }) {
  const refresh = useRefreshProperties();
  const [mode, setMode] = useState<"view" | "edit" | "confirm">("view");
  const archive = useMutation({
    mutationFn: async () => {
      const { response } = await api.POST("/api/app/units/{unit_id}/archive", {
        params: { path: { unit_id: unit.id } },
      });
      return archiveOutcome(response);
    },
    onSuccess: async (outcome) => {
      if (outcome === "archived") {
        await refresh();
      }
    },
  });
  if (mode === "edit") {
    return (
      <li className="rounded-lg border border-stone-300 p-3">
        <UnitEditor
          unit={unit}
          onDone={() => {
            setMode("view");
          }}
        />
      </li>
    );
  }
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-stone-300 p-3">
      <p>
        {unit.name} · {text.unitKinds[unit.kind]}
      </p>
      {mode === "confirm" ? (
        <>
          <p>{text.edit.confirmArchiveUnit(unit.name)}</p>
          <div className="flex gap-3">
            <button
              type="button"
              className={primaryButton}
              disabled={archive.isPending}
              onClick={() => {
                archive.mutate();
              }}
            >
              {text.edit.confirm}
            </button>
            <button
              type="button"
              className={secondaryButton}
              onClick={() => {
                setMode("view");
              }}
            >
              {text.edit.cancel}
            </button>
          </div>
        </>
      ) : (
        <div className="flex gap-3">
          <button
            type="button"
            className={secondaryButton}
            onClick={() => {
              setMode("edit");
            }}
          >
            {text.edit.editUnit(unit.name)}
          </button>
          <button
            type="button"
            className={secondaryButton}
            onClick={() => {
              setMode("confirm");
            }}
          >
            {text.edit.archiveUnit(unit.name)}
          </button>
        </div>
      )}
      {archive.data === "active_lease" && <p role="alert">{text.edit.unitActiveLease}</p>}
      {archive.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
    </li>
  );
}

function AddUnitForm({ propertyId }: { propertyId: string }) {
  const refresh = useRefreshProperties();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UnitValues>({
    resolver: zodResolver(unitSchema),
    defaultValues: { name: "", kind: "room" },
  });
  const mutation = useMutation({
    mutationFn: async (values: UnitValues) => {
      const { response } = await api.POST("/api/app/properties/{property_id}/units", {
        params: { path: { property_id: propertyId } },
        body: { name: values.name.trim(), kind: values.kind },
      });
      expectStatus(response, 201);
    },
    onSuccess: async () => {
      reset();
      await refresh();
    },
  });
  return (
    <form
      noValidate
      aria-labelledby="add-unit-title"
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          mutation.mutate(values);
        })(event);
      }}
    >
      <h3 id="add-unit-title" className="text-lg font-semibold">
        {text.edit.addUnitTitle}
      </h3>
      <UnitInputs idPrefix="new-unit" register={register} errors={errors} />
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      <button type="submit" disabled={mutation.isPending} className={secondaryButton}>
        {text.edit.addUnit}
      </button>
    </form>
  );
}

function ArchiveProperty({ property }: { property: Property }) {
  const navigate = useNavigate();
  const refresh = useRefreshProperties();
  const [confirming, setConfirming] = useState(false);
  const archive = useMutation({
    mutationFn: async () => {
      const { response } = await api.POST("/api/app/properties/{property_id}/archive", {
        params: { path: { property_id: property.id } },
      });
      return archiveOutcome(response);
    },
    onSuccess: async (outcome) => {
      if (outcome === "archived") {
        await refresh();
        await navigate({ to: "/app/inmuebles" });
      }
    },
  });
  return (
    <section className="flex flex-col gap-3">
      {confirming ? (
        <>
          <p>{text.edit.confirmArchiveProperty}</p>
          <div className="flex gap-3">
            <button
              type="button"
              className={primaryButton}
              disabled={archive.isPending}
              onClick={() => {
                archive.mutate();
              }}
            >
              {text.edit.confirm}
            </button>
            <button
              type="button"
              className={secondaryButton}
              onClick={() => {
                setConfirming(false);
              }}
            >
              {text.edit.cancel}
            </button>
          </div>
        </>
      ) : (
        <button
          type="button"
          className={secondaryButton}
          onClick={() => {
            setConfirming(true);
          }}
        >
          {text.edit.archiveProperty}
        </button>
      )}
      {archive.data === "active_lease" && <p role="alert">{text.edit.propertyActiveLease}</p>}
      {archive.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
    </section>
  );
}

function PropertyEditor({ property, estateAccount }: { property: Property; estateAccount: boolean }) {
  if (property.archived) {
    return <p>{text.edit.archivedNotice}</p>;
  }
  const units = property.units.filter((unit) => !unit.archived);
  return (
    <>
      <DetailsForm property={property} estateAccount={estateAccount} />
      <section aria-labelledby="units-title" className="flex flex-col gap-4">
        <h2 id="units-title" className="text-2xl font-bold">
          {text.edit.units}
        </h2>
        <ul className="flex flex-col gap-3">
          {units.map((unit) => (
            <UnitRow key={unit.id} unit={unit} />
          ))}
        </ul>
        <AddUnitForm propertyId={property.id} />
      </section>
      <ArchiveProperty property={property} />
    </>
  );
}

export function EditPropertyPage() {
  const { propertyId } = useParams({ from: "/app/inmuebles/$propertyId" });
  const properties = useQuery({ queryKey: ["properties"], queryFn: fetchProperties });
  const profile = useQuery({ queryKey: ["profile"], queryFn: fetchProfile });

  if (properties.data?.kind === "login" || profile.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  const property =
    properties.data?.kind === "properties"
      ? properties.data.properties.find((item) => item.id === propertyId)
      : undefined;
  const estateAccount =
    profile.data?.kind === "profile" ? profile.data.profile.taxpayer_kind === "estate" : null;
  const ready = properties.data?.kind === "properties" && estateAccount !== null;
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{property?.name ?? text.list.title}</h1>
      {properties.data?.kind === "paused" && <p role="alert">{text.errors.paused}</p>}
      {(properties.isError || profile.isError) && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {ready && !property && <p role="alert">{text.edit.notFound}</p>}
      {ready && property && (
        <PropertyEditor key={property.id} property={property} estateAccount={estateAccount} />
      )}
      <Link to="/app/inmuebles" className={textLink}>
        {text.form.cancel}
      </Link>
    </div>
  );
}
