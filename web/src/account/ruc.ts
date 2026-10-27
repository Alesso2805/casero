import type { components } from "../api/schema";

export type RucGroup = NonNullable<components["schemas"]["ProfileResponse"]["ruc_group"]>;

// Mirrors casero.accounts.domain.profile; the server has the final word.
const RUC_WEIGHTS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
const GROUP_BY_LAST_DIGIT: Record<string, RucGroup> = {
  "0": "0",
  "1": "1",
  "2": "2-3",
  "3": "2-3",
  "4": "4-5",
  "5": "4-5",
  "6": "6-7",
  "7": "6-7",
  "8": "8-9",
  "9": "8-9",
};

export function hasRucShape(ruc: string): boolean {
  return /^[0-9]{11}$/.test(ruc);
}

export function isValidRuc(ruc: string): boolean {
  if (!hasRucShape(ruc)) {
    return false;
  }
  const total = RUC_WEIGHTS.reduce((sum, weight, index) => sum + weight * Number(ruc[index]), 0);
  return (11 - (total % 11)) % 10 === Number(ruc[10]);
}

export function rucGroup(ruc: string, goodTaxpayer: boolean): RucGroup | null {
  if (!isValidRuc(ruc)) {
    return null;
  }
  return goodTaxpayer ? "bc" : (GROUP_BY_LAST_DIGIT[ruc.slice(-1)] ?? null);
}
