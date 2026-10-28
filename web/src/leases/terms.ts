const BYTE = 256;
const TIMESTAMP_BYTES = 6;
const VERSION_7 = 0x70;
const VARIANT_RFC = 0x80;

/** A uuid v7, generated when a form opens so that sending it twice creates nothing (rule 5). */
export function uuidv7(now: number = Date.now()): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let time = now;
  for (let index = TIMESTAMP_BYTES - 1; index >= 0; index -= 1) {
    bytes[index] = time % BYTE;
    time = Math.floor(time / BYTE);
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | VERSION_7;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | VARIANT_RFC;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

const limaDate = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Lima" });

export function limaToday(now: Date = new Date()): string {
  return limaDate.format(now);
}

// Mirrors casero.leases.domain.leases; the server has the final word.
export const FIRST_CONTROL_PERIOD = "2026-01";

function nextPeriod(period: string): string {
  const [year = 0, month = 0] = period.split("-").map(Number);
  return month === 12
    ? `${String(year + 1)}-01`
    : `${String(year)}-${String(month + 1).padStart(2, "0")}`;
}

/** The months the landlord may start control from, oldest first. */
export function controlPeriods(startDate: string, today: string): string[] {
  const current = today.slice(0, 7);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
    return [current];
  }
  const start = startDate.slice(0, 7);
  if (startDate > today) {
    return [start];
  }
  const periods: string[] = [];
  for (let period = start < FIRST_CONTROL_PERIOD ? FIRST_CONTROL_PERIOD : start; period <= current; ) {
    periods.push(period);
    period = nextPeriod(period);
  }
  return periods;
}

const monthName = new Intl.DateTimeFormat("es-PE", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

export function periodLabel(period: string): string {
  const [year = 0, month = 1] = period.split("-").map(Number);
  return monthName.format(new Date(Date.UTC(year, month - 1, 1)));
}
