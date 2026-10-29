import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { primaryButton, secondaryButton } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { formatLimaDay } from "../landing/dates";
import { leasesCopy as text } from "./copy";
import { inputClass } from "./writes";

type Link = components["schemas"]["TenantLinkResponse"];
type Answer = { kind: "link"; link: Link | null } | { kind: "login" } | { kind: "unavailable" };

const t = text.tenantLink;

async function answerOf(
  request: Promise<{ data?: { link?: Link | null } | Link; response: Response }>,
): Promise<Answer> {
  const { data, response } = await request;
  if (data) {
    return { kind: "link", link: "url" in data ? data : (data.link ?? null) };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return { kind: "unavailable" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function TenantLinkBlock({ leaseId }: { leaseId: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [message, setMessage] = useState<string | null>(null);
  const status = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    // After revoking, the buttons that had focus are gone: the confirmation takes it.
    if (message === t.revoked) {
      status.current?.focus();
    }
  }, [message]);
  const key = ["tenant-link", leaseId];
  const params = { params: { path: { lease_id: leaseId } } };
  const current = useQuery({
    queryKey: key,
    queryFn: () => answerOf(api.GET("/api/app/leases/{lease_id}/tenant-link", params)),
  });
  const change = useMutation({
    mutationFn: (action: "issue" | "revoke") =>
      answerOf(
        action === "issue"
          ? api.POST("/api/app/leases/{lease_id}/tenant-link", params)
          : api.POST("/api/app/leases/{lease_id}/tenant-link/revoke", params),
      ),
    onSuccess: (answer, action) => {
      if (answer.kind === "login") {
        void navigate({ to: "/ingresar" });
        return;
      }
      queryClient.setQueryData(key, answer);
      setMessage(answer.kind === "link" && action === "revoke" ? t.revoked : null);
    },
  });
  const answer = change.data?.kind === "unavailable" ? change.data : current.data;
  const link = answer?.kind === "link" ? answer.link : null;
  return (
    <section aria-labelledby="tenant-link-title" className="flex flex-col gap-3">
      <h2 id="tenant-link-title" className="text-2xl font-bold">
        {t.title}
      </h2>
      <p>{t.intro}</p>
      {answer?.kind === "unavailable" && <p role="alert">{t.unavailable}</p>}
      {message && (
        <p ref={status} role="status" tabIndex={-1}>
          {message}
        </p>
      )}
      {(current.isError || change.isError) && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {link ? (
        <>
          <label htmlFor="tenant-link-url" className="font-medium">
            {t.url}
          </label>
          <input
            id="tenant-link-url"
            readOnly
            className={inputClass}
            value={link.url}
            onFocus={(event) => {
              event.target.select();
            }}
          />
          <p className="text-stone-700">
            {link.last_used_at ? t.lastUsed(formatLimaDay(link.last_used_at)) : t.neverUsed}
          </p>
          <button
            type="button"
            className={primaryButton}
            onClick={() => {
              void navigator.clipboard.writeText(link.url).then(() => {
                setMessage(t.copied);
              });
            }}
          >
            {t.copy}
          </button>
          <p id="tenant-link-renew-hint" className="text-stone-600">
            {t.renewHint}
          </p>
          <button
            type="button"
            className={secondaryButton}
            aria-describedby="tenant-link-renew-hint"
            disabled={change.isPending}
            onClick={() => {
              change.mutate("issue");
            }}
          >
            {t.renew}
          </button>
          <button
            type="button"
            className={secondaryButton}
            disabled={change.isPending}
            onClick={() => {
              change.mutate("revoke");
            }}
          >
            {t.revoke}
          </button>
        </>
      ) : (
        answer?.kind === "link" && (
          <button
            type="button"
            className={primaryButton}
            disabled={change.isPending}
            onClick={() => {
              change.mutate("issue");
            }}
          >
            {t.create}
          </button>
        )
      )}
    </section>
  );
}
