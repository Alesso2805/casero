import { Link } from "@tanstack/react-router";

import { leasesCopy as text } from "./copy";
import { periodLabel } from "./terms";

const months = new Intl.ListFormat("es-PE", { type: "conjunction" });

/** After a void that changed months already paid to SUNAT (SPEC, Pagos, "Anulación"). */
export function SunatVoidNotice({ periods }: { periods: string[] }) {
  if (periods.length === 0) {
    return null;
  }
  const labels = months.format(periods.map(periodLabel));
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-amber-50 p-3 text-amber-900">
      <p role="alert">
        {periods.length === 1 ? text.sunatChanged.one(labels) : text.sunatChanged.many(labels)}
      </p>
      <Link to="/app/impuestos" className="inline-flex min-h-11 items-center underline">
        {text.sunatChanged.open}
      </Link>
    </div>
  );
}
