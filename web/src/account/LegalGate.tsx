import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useBusiness } from "../api/business";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { accountCopy as text } from "./copy";
import { DataDownload } from "./DataDownload";
import { DeleteAccount } from "./DeleteAccount";
import { primaryButton } from "./fields";

export type LegalStatus = components["schemas"]["LegalStatusResponse"];
type LegalDocument = components["schemas"]["LegalDocumentResponse"];

export async function fetchLegalStatus(): Promise<LegalStatus | null> {
  const { data, response } = await api.GET("/api/app/legal");
  if (data) {
    return data;
  }
  if (response.status === 401 || response.status === 403) {
    return null;
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function isBlocked(status: LegalStatus | null | undefined): status is LegalStatus {
  return Boolean(status && (status.consent_withdrawn || status.pending.length > 0));
}

async function acceptDocuments(documentIds: string[]): Promise<"accepted" | "outdated"> {
  const { data, response } = await api.POST("/api/app/legal/acceptances", {
    body: { document_ids: documentIds },
  });
  if (data) {
    return "accepted";
  }
  if (response.status === 422) {
    return "outdated";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function DocumentLabel({ document }: { document: LegalDocument }) {
  const business = useBusiness();
  const lead = {
    terms: text.register.acceptTerms,
    privacy: text.legalGate.acceptPrivacy,
    sensitive_consent: text.register.consent(
      business.data?.name ?? text.register.controllerFallback,
    ),
  }[document.kind];
  const name = {
    terms: text.register.terms,
    privacy: text.register.privacy,
    sensitive_consent: text.register.consentLink,
  }[document.kind];
  return (
    <>
      {lead}{" "}
      <a href={document.url} target="_blank" className="text-brand underline">
        {name}
      </a>{" "}
      {text.legalGate.version(document.version)}.
    </>
  );
}

/** Replaces the home page until the user accepts what's pending (SPEC, "Datos personales"). */
export function LegalGate({ status }: { status: LegalStatus }) {
  const queryClient = useQueryClient();
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const accept = useMutation({
    mutationFn: () => acceptDocuments(status.pending.map((document) => document.id)),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  const withdrawn = status.consent_withdrawn;
  return (
    <section aria-labelledby="legal-gate-title" className="flex flex-col gap-4">
      <h2 id="legal-gate-title" className="text-2xl font-bold">
        {withdrawn ? text.legalGate.withdrawnTitle : text.legalGate.updatedTitle}
      </h2>
      <p>{withdrawn ? text.legalGate.withdrawnIntro : text.legalGate.updatedIntro}</p>
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          accept.mutate();
        }}
      >
        {status.pending.map((document) => {
          const id = `legal-${document.id}`;
          return (
            <div key={document.id} className="flex items-start gap-3">
              <input
                id={id}
                type="checkbox"
                className="mt-1 size-6 shrink-0"
                checked={checked.has(document.id)}
                onChange={(event) => {
                  const next = new Set(checked);
                  if (event.target.checked) {
                    next.add(document.id);
                  } else {
                    next.delete(document.id);
                  }
                  setChecked(next);
                }}
              />
              <label htmlFor={id}>
                <DocumentLabel document={document} />
              </label>
            </div>
          );
        })}
        {accept.data === "outdated" && (
          <p role="alert" className="text-red-800">
            {text.legalGate.outdated}
          </p>
        )}
        {accept.isError && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
        <button
          type="submit"
          className={primaryButton}
          disabled={accept.isPending || status.pending.some((d) => !checked.has(d.id))}
        >
          {accept.isPending ? text.legalGate.sending : text.legalGate.submit}
        </button>
      </form>
      <DataDownload />
      <DeleteAccount />
    </section>
  );
}
