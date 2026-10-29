import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { periodLabel } from "../leases/terms";
import { taxCopy } from "./copy";

const text = taxCopy.dueNotice;

type Upcoming = components["schemas"]["UpcomingDueResponse"];

async function fetchUpcoming(): Promise<Upcoming | null> {
  const { data, response } = await api.GET("/api/app/tax/upcoming");
  if (response.ok) {
    return data ?? null;
  }
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function message(upcoming: Upcoming): string {
  const period = periodLabel(upcoming.period);
  const amount = formatSoles(upcoming.pending_cents);
  switch (upcoming.days_left) {
    case 0:
      return text.today(period, amount);
    case 1:
      return text.tomorrow(period, amount);
    default:
      return text.soon(period, formatDay(upcoming.due_on), upcoming.days_left, amount);
  }
}

/** SPEC's fixed notice in the last 5 days before the 1683 falls due. */
export function DueNotice() {
  const upcoming = useQuery({ queryKey: ["tax-upcoming"], queryFn: fetchUpcoming });
  if (!upcoming.data) {
    return null;
  }
  return (
    <section className="flex flex-col gap-2 rounded-lg bg-amber-50 p-4 text-amber-900">
      <p className="font-semibold">{message(upcoming.data)}</p>
      <Link to="/app/impuestos" className="inline-flex min-h-11 items-center underline">
        {text.open}
      </Link>
    </section>
  );
}
