import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { primaryButton } from "../account/fields";
import { fetchProperties } from "../properties/PropertiesPage";
import { leasesCopy as text } from "./copy";

type Lease = components["schemas"]["LeaseResponse"];
type Renter = components["schemas"]["RenterResponse"];
type Property = components["schemas"]["PropertyResponse"];
type Loaded<T> = { kind: "data"; data: T } | { kind: "login" } | { kind: "paused" };

async function loaded<T>(request: Promise<{ data?: T; response: Response }>): Promise<Loaded<T>> {
  const { data, response } = await request;
  if (data) {
    return { kind: "data", data };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return { kind: "paused" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export const fetchLeases = () => loaded(api.GET("/api/app/leases"));
export const fetchRenters = () => loaded(api.GET("/api/app/renters"));

function unitLabels(properties: Property[]): Map<string, string> {
  return new Map(
    properties.flatMap((property) =>
      property.units.map((unit) => [unit.id, `${unit.name} · ${property.name}`] as const),
    ),
  );
}

function EndNotice({ lease }: { lease: Lease }) {
  if (!lease.ending_soon || lease.days_to_end === null) {
    return null;
  }
  return (
    <p className="rounded-lg bg-amber-50 p-3 text-amber-900">
      {lease.days_to_end === 0 ? text.list.endsToday : text.list.endsIn(lease.days_to_end)}
    </p>
  );
}

function LeaseCard({ lease, renter, unit }: { lease: Lease; renter: string; unit: string }) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-stone-300 p-4">
      <h2 className="text-xl font-semibold">{renter}</h2>
      <p>{unit}</p>
      <p>{text.list.rent(formatSoles(lease.monthly_rent_cents))}</p>
      <p>{text.list.dueDay(lease.due_day)}</p>
      <p className="text-stone-600">
        {text.list.since(formatDay(lease.start_date))}
        {lease.end_date && ` · ${text.list.until(formatDay(lease.end_date))}`}
      </p>
      {lease.tax_treatment === "unsupported" && (
        <p className="text-stone-600">{text.list.unsupported}</p>
      )}
      <EndNotice lease={lease} />
      <Link
        to="/app/contratos/$leaseId"
        params={{ leaseId: lease.id }}
        className="min-h-11 py-2 text-brand underline"
        aria-label={text.lease.detailsOf(renter)}
      >
        {text.lease.details}
      </Link>
    </li>
  );
}

export function LeasesPage() {
  const leases = useQuery({ queryKey: ["leases"], queryFn: fetchLeases });
  const renters = useQuery({ queryKey: ["renters"], queryFn: fetchRenters });
  const properties = useQuery({ queryKey: ["properties"], queryFn: fetchProperties });

  if (leases.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  const ready =
    leases.data?.kind === "data" &&
    renters.data?.kind === "data" &&
    properties.data?.kind === "properties";
  const names = new Map(
    renters.data?.kind === "data" ? renters.data.data.map((r: Renter) => [r.id, r.full_name]) : [],
  );
  const units = unitLabels(properties.data?.kind === "properties" ? properties.data.properties : []);
  const all = leases.data?.kind === "data" ? leases.data.data : [];
  const active = all.filter((lease) => lease.ended_at === null);
  const ended = all.filter((lease) => lease.ended_at !== null);
  const card = (lease: Lease) => (
    <LeaseCard
      key={lease.id}
      lease={lease}
      renter={names.get(lease.renter_id) ?? text.list.unknownRenter}
      unit={units.get(lease.unit_id) ?? text.list.unknownUnit}
    />
  );
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.list.title}</h1>
      {leases.data?.kind === "paused" && <p role="alert">{text.errors.paused}</p>}
      {(leases.isError || renters.isError || properties.isError) && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {ready && (
        <>
          {active.length === 0 && <p>{text.list.empty}</p>}
          <Link
            to="/app/contratos/nuevo"
            className={`${primaryButton} flex items-center justify-center`}
          >
            {text.list.add}
          </Link>
          <ul className="flex flex-col gap-4">{active.map(card)}</ul>
          {ended.length > 0 && (
            <details>
              <summary className="min-h-11 cursor-pointer py-2">
                {text.list.ended(ended.length)}
              </summary>
              <ul className="mt-2 flex flex-col gap-4">{ended.map(card)}</ul>
            </details>
          )}
        </>
      )}
      <Link to="/app" className="text-brand underline">
        {text.list.back}
      </Link>
    </div>
  );
}
