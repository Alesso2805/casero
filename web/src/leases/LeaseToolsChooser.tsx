import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { primaryButton } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { leasesCopy as text } from "./copy";

type ToolsStatus = components["schemas"]["ToolsStatusResponse"];

async function fetchLeaseTools(): Promise<ToolsStatus | null> {
  const { data } = await api.GET("/api/app/lease-tools");
  return data ?? null;
}

async function chooseLeaseTools(leaseIds: string[]): Promise<ToolsStatus> {
  const { data } = await api.PUT("/api/app/lease-tools", { body: { lease_ids: leaseIds } });
  if (!data) {
    throw new Error("Lease tools not saved");
  }
  return data;
}

function Chooser({
  status,
  names,
}: {
  status: ToolsStatus;
  names: ReadonlyMap<string, string>;
}) {
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<ReadonlySet<string>>(
    new Set(status.leases.filter((lease) => lease.tools_enabled).map((lease) => lease.lease_id)),
  );
  const save = useMutation({
    mutationFn: () => chooseLeaseTools([...chosen]),
    onSuccess: (updated) => {
      queryClient.setQueryData(["lease-tools"], updated);
    },
  });
  const full = chosen.size >= status.limit;
  return (
    <section
      aria-labelledby="lease-tools-title"
      className="flex flex-col gap-3 rounded-lg bg-amber-50 p-4 text-amber-900"
    >
      <h2 id="lease-tools-title" className="text-xl font-semibold">
        {text.tools.title}
      </h2>
      <p>{text.tools.intro(status.limit)}</p>
      <form
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        {status.leases.map(({ lease_id: id }) => (
          <div key={id} className="flex items-start gap-3">
            <input
              id={`lease-tools-${id}`}
              type="checkbox"
              className="mt-1 size-6 shrink-0"
              checked={chosen.has(id)}
              disabled={full && !chosen.has(id)}
              onChange={(event) => {
                const next = new Set(chosen);
                if (event.target.checked) {
                  next.add(id);
                } else {
                  next.delete(id);
                }
                setChosen(next);
                save.reset();
              }}
            />
            <label htmlFor={`lease-tools-${id}`}>{names.get(id) ?? text.list.unknownRenter}</label>
          </div>
        ))}
        <button type="submit" className={primaryButton} disabled={save.isPending}>
          {save.isPending ? text.tools.sending : text.tools.save}
        </button>
        {save.isSuccess && <p role="status">{text.tools.saved}</p>}
        {save.isError && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
      </form>
    </section>
  );
}

/** Only shows while the account has more active leases than its plan covers. */
export function LeaseToolsChooser({ names }: { names: ReadonlyMap<string, string> }) {
  const tools = useQuery({ queryKey: ["lease-tools"], queryFn: fetchLeaseTools });
  if (!tools.data?.over_limit) {
    return null;
  }
  return <Chooser status={tools.data} names={names} />;
}
