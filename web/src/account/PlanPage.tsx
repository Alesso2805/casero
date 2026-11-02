import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";

import { useBusiness } from "../api/business";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { accountCopy as text } from "./copy";
import { textLink } from "./fields";
import { type Account, fetchAccount } from "./subscription";

type PlanOffer = components["schemas"]["PlanResponse"];

async function fetchPlans(): Promise<PlanOffer[]> {
  const { data } = await api.GET("/api/app/plans");
  if (!data) {
    throw new Error("Plans not loaded");
  }
  return data;
}

function statusText(account: Account): string {
  switch (account.status) {
    case "trial":
      return text.plan.trial(formatDay(account.trial_ends_at ?? ""));
    case "active":
      return account.ends_at ? text.plan.active(formatDay(account.ends_at)) : text.plan.activeOpen;
    case "grace":
      return text.plan.grace(formatDay(account.grace_until ?? ""));
    case "free":
      return text.plan.free;
  }
}

function PlanCard({ plan }: { plan: PlanOffer }) {
  const paid = plan.price_month_cents > 0;
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-stone-300 p-4">
      <h3 className="text-xl font-semibold">{plan.name}</h3>
      <p>
        {paid
          ? text.plan.price(formatSoles(plan.price_month_cents), formatSoles(plan.price_year_cents))
          : text.plan.noPrice}
      </p>
      <p>{text.plan.leases(plan.max_active_leases)}</p>
      <p>{paid ? text.plan.paidFeatures : text.plan.freeFeatures}</p>
    </li>
  );
}

export function PlanPage() {
  const account = useQuery({ queryKey: ["account"], queryFn: fetchAccount });
  const plans = useQuery({ queryKey: ["plans"], queryFn: fetchPlans });
  const business = useBusiness();

  if (account.data === "login") {
    return <Navigate to="/ingresar" />;
  }
  const loaded = account.data !== undefined && account.data !== "paused" ? account.data : null;
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.plan.title}</h1>
      {account.data === "paused" && <p role="alert">{text.profile.paused}</p>}
      {(account.isError || plans.isError) && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {loaded && <p className="font-semibold">{statusText(loaded)}</p>}
      {plans.data && (
        <section aria-labelledby="plans-title" className="flex flex-col gap-3">
          <h2 id="plans-title" className="text-2xl font-bold">
            {text.plan.plansTitle}
          </h2>
          <ul className="flex flex-col gap-3">
            {plans.data.map((plan) => (
              <PlanCard key={plan.code} plan={plan} />
            ))}
          </ul>
        </section>
      )}
      {business.data?.yape && (
        <section aria-labelledby="pay-title" className="flex flex-col gap-2">
          <h2 id="pay-title" className="text-2xl font-bold">
            {text.plan.payTitle}
          </h2>
          <ol className="flex list-decimal flex-col gap-2 pl-5">
            <li>{text.plan.payYape(business.data.yape, business.data.name)}</li>
            <li>{text.plan.payProof}</li>
            <li>{text.plan.payActivation}</li>
          </ol>
        </section>
      )}
      <Link to="/app" className={textLink}>
        {text.profile.back}
      </Link>
    </div>
  );
}
