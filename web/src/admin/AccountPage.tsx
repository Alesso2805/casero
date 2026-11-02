import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";

import { textLink } from "../account/fields";
import { formatDay } from "../landing/dates";
import { formatSoles } from "../landing/money";
import { limaToday } from "../leases/terms";
import { type AccountDetail, adminApi } from "./api";
import { adminCopy as text } from "./copy";
import { PaymentForm } from "./PaymentForm";

async function fetchAccount(accountId: string): Promise<AccountDetail | "not_found"> {
  const { data, response } = await adminApi.GET("/api/admin/accounts/{account_id}", {
    params: { path: { account_id: accountId } },
  });
  if (data) {
    return data;
  }
  if (response.status === 404) {
    return "not_found";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="font-semibold">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Payments({ account }: { account: AccountDetail }) {
  if (account.payments.length === 0) {
    return <p>{text.account.noPayments}</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {account.payments.map((payment) => (
        <li key={payment.id} className="rounded-lg border border-stone-300 p-3">
          {text.account.payment(
            formatSoles(payment.amount_cents),
            formatDay(payment.paid_on),
            payment.months,
            payment.boleta_number,
          )}
        </li>
      ))}
    </ul>
  );
}

function Account({ account }: { account: AccountDetail }) {
  const closing = account.deletion_requested_at !== null || account.purged_at !== null;
  return (
    <>
      <h1 className="text-3xl font-bold break-words">{account.email}</h1>
      <dl className="grid gap-3 sm:grid-cols-2">
        <Fact label={text.account.name} value={account.display_name ?? text.account.noValue} />
        <Fact
          label={text.account.created}
          value={formatDay(limaToday(new Date(account.created_at)))}
        />
        <Fact
          label={text.account.verified}
          value={account.email_verified ? text.account.yes : text.account.no}
        />
        <Fact
          label={text.account.status}
          value={text.status[account.status as keyof typeof text.status]}
        />
        <Fact
          label={text.account.trialEnds}
          value={account.trial_ends_at ? formatDay(account.trial_ends_at) : text.account.noValue}
        />
        <Fact
          label={text.account.ends}
          value={account.ends_at ? formatDay(account.ends_at) : text.account.noValue}
        />
        <Fact
          label={text.account.founder}
          value={account.founder ? text.account.yes : text.account.no}
        />
      </dl>
      <section aria-labelledby="payments-title" className="flex flex-col gap-3">
        <h2 id="payments-title" className="text-2xl font-bold">
          {text.account.paymentsTitle}
        </h2>
        <Payments account={account} />
      </section>
      {closing ? <p role="status">{text.account.closing}</p> : <PaymentForm accountId={account.id} />}
    </>
  );
}

export function AccountPage() {
  const { accountId } = useParams({ from: "/shell/cuentas/$accountId" });
  const account = useQuery({
    queryKey: ["account", accountId],
    queryFn: () => fetchAccount(accountId),
  });

  return (
    <div className="flex flex-col gap-6">
      <Link to="/" className={textLink}>
        {text.account.back}
      </Link>
      {account.isPending && <p>{text.loading}</p>}
      {account.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {account.data === "not_found" && <p role="alert">{text.account.notFound}</p>}
      {account.data && account.data !== "not_found" && <Account account={account.data} />}
    </div>
  );
}
