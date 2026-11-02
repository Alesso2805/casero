import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { primaryButton, TextField, textLink } from "../account/fields";
import { formatDay } from "../landing/dates";
import { type Account, adminApi } from "./api";
import { adminCopy as text } from "./copy";

const schema = z.object({ email: z.string().trim().min(3, text.accounts.tooShort).max(254) });

type SearchValues = z.input<typeof schema>;

async function searchAccounts(email: string): Promise<Account[]> {
  const { data } = await adminApi.GET("/api/admin/accounts", { params: { query: { email } } });
  if (!data) {
    throw new Error("Accounts not loaded");
  }
  return data;
}

function AccountRow({ account }: { account: Account }) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-stone-300 p-4">
      <Link
        to="/cuentas/$accountId"
        params={{ accountId: account.id }}
        className={`${textLink} break-all`}
      >
        {account.email}
      </Link>
      <span>{account.display_name}</span>
      <span>
        {text.status[account.status as keyof typeof text.status]}
        {account.ends_at ? ` · ${formatDay(account.ends_at)}` : ""}
      </span>
    </li>
  );
}

export function AccountsPage() {
  const [searched, setSearched] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SearchValues>({ resolver: zodResolver(schema) });
  const accounts = useQuery({
    queryKey: ["accounts", searched],
    queryFn: () => searchAccounts(searched ?? ""),
    enabled: searched !== null,
  });

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{text.accounts.title}</h1>
      <form
        noValidate
        className="flex max-w-md flex-col gap-4"
        onSubmit={(event) => {
          void handleSubmit((values) => {
            setSearched(values.email.trim());
          })(event);
        }}
      >
        <TextField
          id="email"
          label={text.accounts.search}
          hint={text.accounts.searchHint}
          error={errors.email}
          registration={register("email")}
        />
        <button type="submit" className={primaryButton}>
          {text.accounts.submit}
        </button>
      </form>
      {accounts.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {accounts.data?.length === 0 && <p>{text.accounts.none}</p>}
      {accounts.data && accounts.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {accounts.data.map((account) => (
            <AccountRow key={account.id} account={account} />
          ))}
        </ul>
      )}
    </div>
  );
}
