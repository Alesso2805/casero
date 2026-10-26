import { z } from "zod";

import type { components } from "../../api/schema";
import { parseSolesToCents } from "../money";
import { complaintsCopy } from "./copy";

export type ComplaintRequest = components["schemas"]["FileComplaintRequest"];

const errors = complaintsCopy.errors;
const DNI = /^[0-9]{8}$/;
const OTHER_DOCUMENT = /^[A-Z0-9]{4,20}$/;

function text(max: number) {
  return z.string().trim().max(max);
}

function isEmail(value: string): boolean {
  return z.email().safeParse(value).success;
}

export function normalizeDocument(value: string): string {
  return value.replace(/[\s.-]/g, "").toUpperCase();
}

export const sheetSchema = z
  .object({
    fullName: text(200).min(1, errors.required),
    documentType: z.enum(["dni", "ce", "passport"]),
    documentNumber: text(30).min(1, errors.required),
    address: text(300),
    email: text(254),
    phone: text(30),
    isMinor: z.boolean(),
    guardianName: text(200),
    guardianAddress: text(300),
    guardianPhone: text(30),
    guardianEmail: text(254),
    itemKind: z.enum(["product", "service"]),
    claimedAmount: text(20),
    itemDescription: text(5000),
    kind: z.enum(["claim", "complaint"]),
    detail: text(5000).min(1, errors.required),
    request: text(5000),
    responseChannel: z.enum(["email", "letter"]),
  })
  .superRefine((sheet, context) => {
    const issue = (path: string, message: string) => {
      context.addIssue({ code: "custom", path: [path], message });
    };
    const document = normalizeDocument(sheet.documentNumber);
    if (document && sheet.documentType === "dni" && !DNI.test(document)) {
      issue("documentNumber", errors.dni);
    }
    if (document && sheet.documentType !== "dni" && !OTHER_DOCUMENT.test(document)) {
      issue("documentNumber", errors.document);
    }
    if (sheet.email && !isEmail(sheet.email)) {
      issue("email", errors.email);
    } else if (sheet.responseChannel === "email" && !sheet.email) {
      issue("email", errors.needsEmail);
    }
    if (sheet.responseChannel === "letter" && !sheet.address) {
      issue("address", errors.needsAddress);
    }
    if (sheet.isMinor && !sheet.guardianName) {
      issue("guardianName", errors.required);
    }
    if (sheet.isMinor && sheet.guardianEmail && !isEmail(sheet.guardianEmail)) {
      issue("guardianEmail", errors.email);
    }
    if (sheet.claimedAmount && parseSolesToCents(sheet.claimedAmount) === null) {
      issue("claimedAmount", errors.amount);
    }
  });

export type SheetValues = z.input<typeof sheetSchema>;

export const emptySheet: SheetValues = {
  fullName: "",
  documentType: "dni",
  documentNumber: "",
  address: "",
  email: "",
  phone: "",
  isMinor: false,
  guardianName: "",
  guardianAddress: "",
  guardianPhone: "",
  guardianEmail: "",
  itemKind: "service",
  claimedAmount: "",
  itemDescription: "",
  kind: "claim",
  detail: "",
  request: "",
  responseChannel: "email",
};

function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

export function toRequest(sheet: SheetValues): ComplaintRequest {
  return {
    full_name: sheet.fullName.trim(),
    document_type: sheet.documentType,
    document_number: normalizeDocument(sheet.documentNumber),
    address: orNull(sheet.address),
    email: orNull(sheet.email),
    phone: orNull(sheet.phone),
    guardian: sheet.isMinor
      ? {
          full_name: sheet.guardianName.trim(),
          address: orNull(sheet.guardianAddress),
          phone: orNull(sheet.guardianPhone),
          email: orNull(sheet.guardianEmail),
        }
      : null,
    item_kind: sheet.itemKind,
    claimed_amount_cents: sheet.claimedAmount ? parseSolesToCents(sheet.claimedAmount) : null,
    item_description: orNull(sheet.itemDescription),
    kind: sheet.kind,
    detail: sheet.detail.trim(),
    request: orNull(sheet.request),
    response_channel: sheet.responseChannel,
  };
}
