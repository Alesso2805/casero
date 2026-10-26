import type { ReactNode } from "react";

import type { Business } from "../../api/business";
import { formatSoles } from "../money";
import { complaintsCopy as text } from "./copy";
import type { ComplaintRequest } from "./sheet";

export interface Filing {
  number: string;
  filedAt: string;
}

const limaTime = new Intl.DateTimeFormat("es-PE", {
  timeZone: "America/Lima",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatLimaTime(isoDateTime: string): string {
  return limaTime.format(new Date(isoDateTime));
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:gap-2">
      <dt className="font-semibold">{label}:</dt>
      <dd className="break-words">{value ?? text.empty}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1">
      <h3 className="text-lg font-bold">{title}</h3>
      <dl className="flex flex-col gap-1">{children}</dl>
    </section>
  );
}

export function ComplaintSheet({
  sheet,
  business,
  filing,
}: {
  sheet: ComplaintRequest;
  business: Business | undefined;
  filing?: Filing | undefined;
}) {
  const amount = sheet.claimed_amount_cents;
  return (
    <article className="flex flex-col gap-4 rounded-lg border border-stone-300 p-4 text-base">
      <header className="flex flex-col gap-1">
        <p className="font-bold uppercase">{text.title}</p>
        <p className="font-bold uppercase">
          {text.sheetTitle} N.° {filing?.number ?? text.numberPending}
        </p>
        {filing && (
          <p>
            {text.filedAt}: {formatLimaTime(filing.filedAt)} ({text.limaTime})
          </p>
        )}
        {business && (
          <>
            <p>
              {text.provider}: {business.name}, RUC {business.ruc}
            </p>
            <p>
              {text.providerAddress}: {business.address}
            </p>
          </>
        )}
      </header>
      <Section title={text.consumer.title}>
        <Field label={text.consumer.fullName} value={sheet.full_name} />
        <Field
          label={text.consumer.documentTypes[sheet.document_type]}
          value={sheet.document_number}
        />
        <Field label={text.consumer.address} value={sheet.address} />
        <Field label={text.sheetLabels.phone} value={sheet.phone} />
        <Field label={text.consumer.email} value={sheet.email} />
        {sheet.guardian && (
          <>
            <Field label={text.consumer.guardian} value={sheet.guardian.full_name} />
            <Field label={text.sheetLabels.guardianAddress} value={sheet.guardian.address} />
            <Field label={text.sheetLabels.guardianPhone} value={sheet.guardian.phone} />
            <Field label={text.sheetLabels.guardianEmail} value={sheet.guardian.email} />
          </>
        )}
      </Section>
      <Section title={text.item.title}>
        <Field label={text.item.kind} value={text.item.kinds[sheet.item_kind]} />
        <Field
          label={text.sheetLabels.amount}
          value={amount == null ? null : formatSoles(amount)}
        />
        <Field label={text.sheetLabels.description} value={sheet.item_description} />
      </Section>
      <Section title={text.claim.title}>
        <Field label={text.claim.kind} value={text.claim.kinds[sheet.kind].label} />
        <Field label={text.claim.detail} value={sheet.detail} />
        <Field label={text.sheetLabels.request} value={sheet.request} />
      </Section>
      <dl>
        <Field label={text.channel.title} value={text.channel.review[sheet.response_channel]} />
      </dl>
    </article>
  );
}
