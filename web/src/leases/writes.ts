import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

export type Outcome =
  | { kind: "done" }
  | { kind: "conflict" }
  | { kind: "login" }
  | { kind: "refused"; detail: string };

export const inputClass = "min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base";

export async function outcomeOf(
  request: Promise<{ data?: unknown; error?: unknown; response: Response }>,
): Promise<Outcome> {
  const { data, error, response } = await request;
  if (data !== undefined) {
    return { kind: "done" };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 409) {
    return { kind: "conflict" };
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (response.status === 422 && typeof detail === "string") {
    return { kind: "refused", detail };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

/** A write on one lease: whatever happens, its statement and the lease list reload. */
export function useLeaseWrite(leaseId: string, write: () => Promise<Outcome>) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: write,
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: ["statement", leaseId] });
      await queryClient.invalidateQueries({ queryKey: ["leases"] });
    },
    onSuccess: (outcome) => {
      if (outcome.kind === "login") {
        void navigate({ to: "/ingresar" });
      }
    },
  });
}
