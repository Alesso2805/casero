import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { periodLabel } from "../leases/terms";
import { accountCopy as text } from "./copy";
import { fetchAccount } from "./subscription";

type PendingDue = components["schemas"]["PendingDueResponse"];

async function fetchPendingDues(): Promise<PendingDue[]> {
  const { data } = await api.GET("/api/app/tax/pending-dues");
  return data ?? [];
}

/** SPEC's notice in the app when the trial ends unpaid, with what's still owed to SUNAT. */
export function TrialNotice() {
  const account = useQuery({ queryKey: ["account"], queryFn: fetchAccount });
  const lapsing =
    typeof account.data === "object" &&
    account.data.status === "grace" &&
    account.data.trial_ends_at === account.data.ends_at
      ? account.data
      : null;
  const dues = useQuery({
    queryKey: ["tax-pending-dues"],
    queryFn: fetchPendingDues,
    enabled: lapsing !== null,
  });
  if (!lapsing) {
    return null;
  }
  return (
    <section className="flex flex-col gap-2 rounded-lg bg-amber-50 p-4 text-amber-900">
      <p className="font-semibold">{text.trialNotice.ended(formatDay(lapsing.grace_until ?? ""))}</p>
      {dues.data && dues.data.length > 0 && (
        <>
          <p>{text.trialNotice.owed}</p>
          <ul className="list-disc pl-5">
            {dues.data.map((due) => (
              <li key={due.period}>
                {text.trialNotice.due(
                  periodLabel(due.period),
                  formatSoles(due.pending_cents),
                  formatDay(due.due_on),
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      <Link to="/app/plan" className="inline-flex min-h-11 items-center underline">
        {text.trialNotice.open}
      </Link>
    </section>
  );
}
