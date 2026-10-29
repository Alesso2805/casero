import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { primaryButton } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { leasesCopy } from "../leases/copy";
import { fetchLeases, fetchRenters } from "../leases/LeasesPage";
import { fetchProperties } from "../properties/PropertiesPage";
import { WhatsAppButton } from "../reminders/WhatsAppButton";
import { collectionsCopy as text } from "./copy";

type Collections = components["schemas"]["CollectionsResponse"];
type Line = components["schemas"]["LeaseCollectionResponse"];
type Loaded = { kind: "collections"; collections: Collections } | { kind: "unavailable" };

const URGENCY: Line["status"][] = ["overdue", "due_today", "due_soon", "up_to_date"];

async function fetchLastReminders(): Promise<Map<string, number>> {
  const { data, response } = await api.GET("/api/app/whatsapp-reminders");
  if (!data) {
    throw new Error(`Unexpected status ${String(response.status)}`);
  }
  return new Map(data.map((reminder) => [reminder.lease_id, reminder.days_ago]));
}

async function fetchCollections(): Promise<Loaded> {
  const { data, response } = await api.GET("/api/app/collections");
  if (data) {
    return { kind: "collections", collections: data };
  }
  if (response.status === 401 || response.status === 403) {
    return { kind: "unavailable" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function detail(line: Line): string {
  const next = line.next_due_on ? formatDay(line.next_due_on) : "";
  switch (line.status) {
    case "overdue":
      return text.overdue(formatSoles(line.overdue_cents), line.overdue_days);
    case "due_today":
      return text.dueToday(formatSoles(line.next_due_cents));
    case "due_soon":
      return text.dueSoon(formatSoles(line.next_due_cents), next);
    case "up_to_date":
      if (line.next_due_on) {
        return text.nextDue(formatSoles(line.next_due_cents), next);
      }
      return line.balance_cents < 0
        ? text.inFavor(formatSoles(-line.balance_cents))
        : text.nothingDue;
  }
}

function useNames() {
  const leases = useQuery({ queryKey: ["leases"], queryFn: fetchLeases });
  const renters = useQuery({ queryKey: ["renters"], queryFn: fetchRenters });
  const properties = useQuery({ queryKey: ["properties"], queryFn: fetchProperties });
  const renterNames = new Map(
    renters.data?.kind === "data" ? renters.data.data.map((r) => [r.id, r.full_name]) : [],
  );
  const unitNames = new Map(
    properties.data?.kind === "properties"
      ? properties.data.properties.flatMap((p) =>
          p.units.map((u) => [u.id, `${u.name} · ${p.name}`] as const),
        )
      : [],
  );
  const byLease = new Map(
    leases.data?.kind === "data"
      ? leases.data.data.map((lease) => [
          lease.id,
          {
            renter: renterNames.get(lease.renter_id) ?? leasesCopy.list.unknownRenter,
            unit: unitNames.get(lease.unit_id) ?? leasesCopy.list.unknownUnit,
          },
        ])
      : [],
  );
  return (leaseId: string) =>
    byLease.get(leaseId) ?? {
      renter: leasesCopy.list.unknownRenter,
      unit: leasesCopy.list.unknownUnit,
    };
}

function LeaseLine({
  line,
  renter,
  unit,
  remindedDaysAgo,
}: {
  line: Line;
  renter: string;
  unit: string;
  remindedDaysAgo: number | undefined;
}) {
  return (
    <li className="rounded-lg border border-stone-300">
      <Link
        to="/app/contratos/$leaseId"
        params={{ leaseId: line.lease_id }}
        className="flex min-h-11 flex-col gap-1 p-3"
      >
        <span className="text-lg font-semibold text-brand underline">{renter}</span>
        <span className="text-stone-700">{unit}</span>
        <span className={line.status === "overdue" ? "font-semibold text-red-800" : ""}>
          {detail(line)}
        </span>
        {line.ended && <span className="text-stone-600">{text.ended}</span>}
        {remindedDaysAgo !== undefined && line.status !== "up_to_date" && (
          <span className="text-stone-600">{text.reminded(remindedDaysAgo)}</span>
        )}
      </Link>
      {line.status !== "up_to_date" && (
        <div className="px-3 pb-3">
          <WhatsAppButton leaseId={line.lease_id} renterName={renter} />
        </div>
      )}
    </li>
  );
}

export function CollectionsPanel() {
  const loaded = useQuery({ queryKey: ["collections"], queryFn: fetchCollections });
  const names = useNames();
  const reminded = useQuery({
    queryKey: ["whatsapp-reminders"],
    queryFn: fetchLastReminders,
    enabled: loaded.data?.kind === "collections" && loaded.data.collections.leases.length > 0,
  });

  if (loaded.isError) {
    return (
      <p role="alert" className="text-red-800">
        {text.failure}
      </p>
    );
  }
  if (loaded.isPending) {
    return <p role="status">{text.loading}</p>;
  }
  if (loaded.data.kind !== "collections") {
    return null;
  }
  const { leases, due_by_month_end_cents, overdue_cents } = loaded.data.collections;
  return (
    <section aria-labelledby="collections-title" className="flex flex-col gap-4">
      <h2 id="collections-title" className="text-2xl font-bold">
        {text.title}
      </h2>
      {leases.length === 0 ? (
        <>
          <p>{text.empty}</p>
          <Link
            to="/app/contratos/nuevo"
            className={`${primaryButton} flex items-center justify-center`}
          >
            {text.addLease}
          </Link>
        </>
      ) : (
        <>
          <div className="flex flex-col gap-1 rounded-lg bg-stone-100 p-4">
            <p className="text-xl font-semibold">
              {text.dueByMonthEnd(formatSoles(due_by_month_end_cents))}
            </p>
            {overdue_cents > 0 && (
              <p className="text-red-800">{text.overdueTotal(formatSoles(overdue_cents))}</p>
            )}
          </div>
          {URGENCY.map((status) => {
            const group = leases.filter((line) => line.status === status);
            return (
              group.length > 0 && (
                <section key={status} aria-labelledby={`group-${status}`}>
                  <h3 id={`group-${status}`} className="mb-2 text-xl font-semibold">
                    {text.groups[status]}
                  </h3>
                  <ul className="flex flex-col gap-2">
                    {group.map((line) => (
                      <LeaseLine
                        key={line.lease_id}
                        line={line}
                        remindedDaysAgo={reminded.data?.get(line.lease_id)}
                        {...names(line.lease_id)}
                      />
                    ))}
                  </ul>
                </section>
              )
            );
          })}
        </>
      )}
    </section>
  );
}
