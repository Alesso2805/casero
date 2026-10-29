import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { leasesCopy as text } from "./copy";
import { periodLabel } from "./terms";

type ChargeLine = components["schemas"]["ChargeLineResponse"];

const DAY_MS = 86_400_000;

interface ChargeView {
  kind: ChargeLine["kind"];
  period: string | null;
  pre_2026: boolean | null;
  amount_cents: number;
}

interface ChargeState {
  voided: boolean;
  status: ChargeLine["status"];
  due_date: string;
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(to) - Date.parse(from)) / DAY_MS);
}

/** How the landlord's page and the tenant's portal name a charge. */
export function chargeLabel(charge: ChargeView): string {
  if (charge.kind === "opening_balance") {
    return charge.pre_2026 ? text.lease.preDebt : text.lease.debt2026;
  }
  if (charge.kind === "adjustment") {
    return charge.amount_cents < 0 ? text.lease.credit : text.lease.adjustment;
  }
  const label = periodLabel(charge.period ?? "");
  const month = label.charAt(0).toUpperCase() + label.slice(1);
  return charge.kind === "rent_correction" ? text.charge.corrected(month) : month;
}

export function statusText(charge: ChargeState, today: string): string {
  if (charge.voided) {
    return text.lease.voided;
  }
  switch (charge.status) {
    case "paid":
      return text.lease.statuses.paid;
    case "overdue":
      return text.lease.statuses.overdue(daysBetween(charge.due_date, today));
    case "due_today":
      return text.lease.statuses.due_today;
    case "due_soon":
      return text.lease.statuses.due_soon(formatDay(charge.due_date));
    case "pending":
      return text.lease.statuses.pending(formatDay(charge.due_date));
    default:
      return "";
  }
}
