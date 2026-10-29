import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { secondaryButton } from "../account/fields";
import { api } from "../api/client";
import { remindersCopy as text } from "./copy";

const REFUSALS: Record<string, string> = text.errors;

async function prepare(leaseId: string): Promise<{ url: string } | { refusal: string }> {
  const { data, error } = await api.POST("/api/app/leases/{lease_id}/whatsapp-reminders", {
    params: { path: { lease_id: leaseId } },
  });
  if (data) {
    return { url: data.url };
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return { refusal: (typeof detail === "string" ? REFUSALS[detail] : undefined) ?? text.errors.failure };
}

export function WhatsAppButton({ leaseId, renterName }: { leaseId: string; renterName: string }) {
  const queryClient = useQueryClient();
  const [sending, setSending] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function send() {
    setRefusal(null);
    setSending(true);
    // Opened during the tap, before the request, so the browser doesn't block it as a popup.
    const tab = window.open("about:blank", "_blank");
    if (tab) {
      tab.opener = null;
    }
    try {
      const prepared = await prepare(leaseId);
      if ("url" in prepared) {
        if (tab) {
          tab.location.href = prepared.url;
        } else {
          window.location.assign(prepared.url);
        }
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["whatsapp-reminders"] }),
          queryClient.invalidateQueries({ queryKey: ["tenant-link", leaseId] }),
        ]);
        return;
      }
      tab?.close();
      setRefusal(prepared.refusal);
    } catch {
      tab?.close();
      setRefusal(text.errors.failure);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        className={secondaryButton}
        aria-label={text.sendTo(renterName)}
        disabled={sending}
        onClick={() => {
          void send();
        }}
      >
        {sending ? text.sending : text.send}
      </button>
      {refusal && (
        <p role="alert" className="text-red-800">
          {refusal}
        </p>
      )}
    </div>
  );
}
