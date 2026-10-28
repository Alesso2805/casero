import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { primaryButton, textLink } from "../account/fields";
import { propertiesCopy as text } from "./copy";

type Property = components["schemas"]["PropertyResponse"];
type Loaded =
  | { kind: "properties"; properties: Property[] }
  | { kind: "login" }
  | { kind: "paused" };

export async function fetchProperties(): Promise<Loaded> {
  const { data, response } = await api.GET("/api/app/properties");
  if (data) {
    return { kind: "properties", properties: data };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return { kind: "paused" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function PropertyCard({ property }: { property: Property }) {
  const units = property.units.filter((unit) => !unit.archived);
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-stone-300 p-4">
      <h2 className="text-xl font-semibold">{property.name}</h2>
      {property.district && <p className="text-stone-600">{property.district}</p>}
      <p>{text.list.units(units.length)}</p>
      <ul className="flex flex-col gap-1">
        {units.map((unit) => (
          <li key={unit.id}>
            {unit.name} · {text.unitKinds[unit.kind]}
          </li>
        ))}
      </ul>
      <Link
        to="/app/inmuebles/$propertyId"
        params={{ propertyId: property.id }}
        className="min-h-11 py-2 text-brand underline"
        aria-label={text.list.detailsOf(property.name)}
      >
        {text.list.details}
      </Link>
    </li>
  );
}

export function PropertiesPage() {
  const loaded = useQuery({ queryKey: ["properties"], queryFn: fetchProperties });

  if (loaded.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  const properties = loaded.data?.kind === "properties" ? loaded.data.properties : null;
  const active = properties?.filter((property) => !property.archived) ?? [];
  const archived = properties?.filter((property) => property.archived) ?? [];
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.list.title}</h1>
      {loaded.data?.kind === "paused" && <p role="alert">{text.errors.paused}</p>}
      {loaded.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {properties && (
        <>
          {active.length === 0 && <p>{text.list.empty}</p>}
          <Link
            to="/app/inmuebles/nuevo"
            className={`${primaryButton} flex items-center justify-center`}
          >
            {text.list.add}
          </Link>
          <ul className="flex flex-col gap-4">
            {active.map((property) => (
              <PropertyCard key={property.id} property={property} />
            ))}
          </ul>
          {archived.length > 0 && (
            <details>
              <summary className="min-h-11 cursor-pointer py-2">
                {text.list.archived(archived.length)}
              </summary>
              <ul className="mt-2 flex flex-col gap-1">
                {archived.map((property) => (
                  <li key={property.id}>{property.name}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      <Link to="/app" className={textLink}>
        {text.list.back}
      </Link>
    </div>
  );
}
