import { useQuery } from "@tanstack/react-query";

import { formatDay } from "../landing/dates";
import { limaToday } from "../leases/terms";
import { adminApi, type ComplaintDeadline } from "./api";
import { adminCopy as text } from "./copy";

async function fetchComplaints(): Promise<ComplaintDeadline[]> {
  const { data } = await adminApi.GET("/api/admin/complaints");
  if (!data) {
    throw new Error("Complaints not loaded");
  }
  return data;
}

function Complaint({ complaint }: { complaint: ComplaintDeadline }) {
  const overdue = complaint.state === "overdue";
  return (
    <li
      className={`flex flex-col gap-1 rounded-lg border p-4 ${
        overdue ? "border-red-800" : "border-stone-300"
      }`}
    >
      <span className="font-semibold">
        {complaint.number} · {text.complaints.kinds[complaint.kind as "claim" | "complaint"]}
      </span>
      <span className={overdue ? "font-semibold text-red-800" : undefined}>
        {text.complaints.states[complaint.state]}
      </span>
      <span>{text.complaints.filed(formatDay(limaToday(new Date(complaint.filed_at))))}</span>
      <span>{text.complaints.due(formatDay(complaint.due_on))}</span>
      <span>
        {text.complaints.channel(
          text.complaints.channels[complaint.response_channel as "email" | "letter"],
        )}
      </span>
    </li>
  );
}

export function ComplaintsPage() {
  const complaints = useQuery({ queryKey: ["complaints"], queryFn: fetchComplaints });

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{text.complaints.title}</h1>
      <p>{text.complaints.where}</p>
      {complaints.isPending && <p>{text.loading}</p>}
      {complaints.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {complaints.data?.length === 0 && <p>{text.complaints.none}</p>}
      {complaints.data && complaints.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {complaints.data.map((complaint) => (
            <Complaint key={complaint.number} complaint={complaint} />
          ))}
        </ul>
      )}
    </div>
  );
}
