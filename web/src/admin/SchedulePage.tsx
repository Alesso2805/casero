import { useQuery } from "@tanstack/react-query";

import { textLink } from "../account/fields";
import { formatDay } from "../landing/dates";
import { periodLabel } from "../leases/terms";
import { adminApi, type ScheduleEntry } from "./api";
import { adminCopy as text } from "./copy";

const GROUPS = ["0", "1", "2-3", "4-5", "6-7", "8-9", "bc"];

async function fetchSchedule(): Promise<ScheduleEntry[]> {
  const { data } = await adminApi.GET("/api/admin/sunat-schedule");
  if (!data) {
    throw new Error("Schedule not loaded");
  }
  return data;
}

function byPeriod(entries: ScheduleEntry[]): Map<string, Map<string, string>> {
  const periods = new Map<string, Map<string, string>>();
  for (const entry of entries) {
    const dates = periods.get(entry.period) ?? new Map<string, string>();
    dates.set(entry.ruc_group, entry.due_on);
    periods.set(entry.period, dates);
  }
  return periods;
}

function ScheduleTable({ entries }: { entries: ScheduleEntry[] }) {
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={text.schedule.title}>
      <table className="w-full border-collapse text-left">
        <thead>
          <tr>
            <th scope="col" className="p-2">
              {text.schedule.period}
            </th>
            {GROUPS.map((group) => (
              <th key={group} scope="col" className="p-2 whitespace-nowrap">
                {group === "bc" ? text.schedule.goodTaxpayers : text.schedule.group(group)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...byPeriod(entries)].map(([period, dates]) => (
            <tr key={period} className="border-t border-stone-300">
              <th scope="row" className="p-2 text-left font-medium whitespace-nowrap">
                {periodLabel(period)}
              </th>
              {GROUPS.map((group) => {
                const due = dates.get(group);
                return (
                  <td key={group} className="p-2 whitespace-nowrap">
                    {due ? formatDay(due) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SchedulePage() {
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: fetchSchedule });
  const sources = [...new Set(schedule.data?.map((entry) => entry.source_url))];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{text.schedule.title}</h1>
      <p>{text.schedule.readOnly}</p>
      {schedule.isPending && <p>{text.loading}</p>}
      {schedule.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {schedule.data?.length === 0 && <p role="alert">{text.schedule.empty}</p>}
      {schedule.data && schedule.data.length > 0 && <ScheduleTable entries={schedule.data} />}
      {sources.map((source) => (
        <a key={source} href={source} rel="noreferrer" target="_blank" className={textLink}>
          {text.schedule.source}
        </a>
      ))}
    </div>
  );
}
