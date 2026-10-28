const CENTS_PER_SOL = 100;
const SOLES = /^(\d{1,9})(?:[.,](\d{1,2}))?$/;

export function parseSolesToCents(text: string): number | null {
  const match = SOLES.exec(text.trim().replace(/^S\/\s*/i, ""));
  if (!match) {
    return null;
  }
  const [, soles = "0", decimals = ""] = match;
  return Number(soles) * CENTS_PER_SOL + Number(decimals.padEnd(2, "0"));
}

export function solesInput(cents: number): string {
  const soles = String(Math.trunc(cents / CENTS_PER_SOL));
  const rest = cents % CENTS_PER_SOL;
  return rest === 0 ? soles : `${soles}.${String(rest).padStart(2, "0")}`;
}

export function formatSoles(cents: number): string {
  const absolute = Math.abs(cents);
  const soles = Math.trunc(absolute / CENTS_PER_SOL);
  const rest = String(absolute % CENTS_PER_SOL).padStart(2, "0");
  return `${cents < 0 ? "-" : ""}S/ ${soles.toLocaleString("en-US")}.${rest}`;
}
