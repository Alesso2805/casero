export function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-");
  return `${day ?? ""}/${month ?? ""}/${year ?? ""}`;
}

const limaDay = new Intl.DateTimeFormat("es-PE", {
  timeZone: "America/Lima",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/** The day in Lima of an instant the API sends in UTC. */
export function formatLimaDay(isoDateTime: string): string {
  return limaDay.format(new Date(isoDateTime));
}
