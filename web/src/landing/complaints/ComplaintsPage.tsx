import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { useBusiness } from "../../api/business";
import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { PublicFooter } from "../PublicFooter";
import { ComplaintForm } from "./ComplaintForm";
import { ComplaintSheet, formatDay } from "./ComplaintSheet";
import { complaintsCopy as text } from "./copy";
import { toRequest, type ComplaintRequest } from "./sheet";

type Filed = components["schemas"]["FiledComplaintResponse"];
type Outcome = { kind: "filed"; filed: Filed } | { kind: "limited" };

async function fileComplaint(sheet: ComplaintRequest): Promise<Outcome> {
  const { data, response } = await api.POST("/api/public/complaints", { body: sheet });
  if (data) {
    return { kind: "filed", filed: data };
  }
  if (response.status === 429) {
    return { kind: "limited" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

const primaryButton =
  "min-h-11 rounded-lg bg-brand px-5 text-base font-semibold text-white hover:bg-brand-dark disabled:opacity-60";
const secondaryButton =
  "min-h-11 rounded-lg border border-brand px-5 text-base font-semibold text-brand";

function PrintButton() {
  return (
    <button
      type="button"
      className={`${primaryButton} print:hidden`}
      onClick={() => {
        globalThis.print();
      }}
    >
      {text.filed.print}
    </button>
  );
}

export function ComplaintsPage() {
  const business = useBusiness();
  const [sheet, setSheet] = useState<ComplaintRequest | null>(null);
  const mutation = useMutation({ mutationFn: fileComplaint });
  const filed = mutation.data?.kind === "filed" ? mutation.data.filed : null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <Link to="/" className="text-brand underline print:hidden">
        {text.filed.back}
      </Link>
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-bold">{text.title}</h1>
        <p className="print:hidden">{text.intro}</p>
        {business.data && (
          <p className="print:hidden">
            {text.provider}: {business.data.name}, RUC {business.data.ruc}.{" "}
            {text.providerAddress}: {business.data.address}.
          </p>
        )}
      </header>

      {filed && sheet ? (
        <section className="flex flex-col gap-4" aria-labelledby="filed-title">
          <div role="status" className="flex flex-col gap-2 rounded-lg bg-emerald-50 p-4 text-emerald-900">
            <h2 id="filed-title" className="text-2xl font-bold">
              {text.filed.title[sheet.kind]}
            </h2>
            <p>
              {text.filed.number}: <strong>{filed.number}</strong>
            </p>
            <p>
              {text.filed.dueOn} {formatDay(filed.due_on)}.
            </p>
            {sheet.email && <p>{text.filed.copyWillBeSent(sheet.email)}</p>}
          </div>
          <PrintButton />
          <ComplaintSheet
            sheet={sheet}
            business={business.data}
            filing={{ number: filed.number, filedAt: filed.filed_at }}
          />
        </section>
      ) : (
        <>
          <div hidden={sheet !== null}>
            <ComplaintForm
              onReview={(values) => {
                mutation.reset();
                setSheet(toRequest(values));
              }}
            />
          </div>
          {sheet && (
            <section className="flex flex-col gap-4" aria-labelledby="review-title">
              <h2 id="review-title" className="text-2xl font-bold">
                {text.review.title}
              </h2>
              <p>{text.review.body}</p>
              <ComplaintSheet sheet={sheet} business={business.data} />
              {mutation.data?.kind === "limited" && (
                <p role="alert" className="text-red-800">
                  {text.errors.tooManyAttempts}
                </p>
              )}
              {mutation.isError && (
                <div role="alert" className="flex flex-col gap-3 text-red-800">
                  <p>
                    {business.data
                      ? text.errors.fallback(business.data.complaints_inbox)
                      : text.errors.failure}
                  </p>
                  {business.data && <PrintButton />}
                </div>
              )}
              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  className={primaryButton}
                  disabled={mutation.isPending}
                  onClick={() => {
                    mutation.mutate(sheet);
                  }}
                >
                  {mutation.isPending ? text.review.sending : text.review.send}
                </button>
                <button
                  type="button"
                  className={secondaryButton}
                  disabled={mutation.isPending}
                  onClick={() => {
                    setSheet(null);
                  }}
                >
                  {text.review.edit}
                </button>
              </div>
            </section>
          )}
        </>
      )}

      <section className="flex flex-col gap-2 border-t border-stone-300 pt-4">
        {text.notices.map((notice) => (
          <p key={notice}>{notice}</p>
        ))}
      </section>
      <PublicFooter />
    </div>
  );
}
