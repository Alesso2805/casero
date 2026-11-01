import { expect, test } from "vitest";

import consent from "../../../docs/legal/sensitive-consent.md?raw";
import privacy from "../../../docs/legal/privacy.md?raw";
import terms from "../../../docs/legal/terms.md?raw";
import { testBusiness } from "../test/api";
import { withBusiness } from "./LegalArticle";
import { LEGAL_DOCUMENTS, legalDocument } from "./legalDocuments";

const DOCUMENTS = { terms, privacy, consent };

// Yours to fill in with the lawyer and the accountant. The landing is published only when this
// list is empty and the draft notices are gone (SPEC, "Antes de publicar la landing").
const PENDING_BEFORE_PUBLISHING = [
  "consent: fecha de publicación",
  "privacy: fecha de publicación",
  "privacy: nombre del banco de datos",
  "privacy: código de inscripción",
  "privacy: plazo que indique el contador; propuesta: 5 años",
  "privacy: ⚑ base legal",
  "privacy: ⚑ cláusulas modelo",
  "privacy: ⚑ confirmar domicilio",
  "privacy: ⚑ confirmar domicilio",
  "privacy: ⚑ confirmar domicilio",
  "terms: fecha de publicación",
  "terms: correo de atención",
  "terms: tipo de comprobante: boleta electrónica",
  "terms: Devoluciones: lo que defina el abogado, incluida la promesa de la preventa.",
  "terms: Cláusula de jurisdicción: lo que defina el abogado.",
];

function placeholders(name: string, text: string): string[] {
  return [...withBusiness(text, testBusiness).matchAll(/\[([^\]]+)\](?!\()/g)].map(
    (match) => `${name}: ${match[1] ?? ""}`,
  );
}

test("the business data fills its placeholders and only the known pending ones remain", () => {
  const remaining = Object.entries(DOCUMENTS).flatMap(([name, text]) => placeholders(name, text));

  expect(remaining.sort()).toEqual([...PENDING_BEFORE_PUBLISHING].sort());
});

test("the privacy contact comes from the server's environment", () => {
  expect(withBusiness(privacy, testBusiness)).toContain(testBusiness.privacy_inbox);
  expect(withBusiness(privacy, testBusiness)).not.toContain("[correo de privacidad]");
});

test("each listed version is the one its text says", () => {
  for (const versions of Object.values(LEGAL_DOCUMENTS)) {
    for (const [version, text] of Object.entries(versions)) {
      expect(text).toContain(`Versión ${version} ·`);
    }
  }
});

test("a link to a version shows that version and an unknown one shows nothing", () => {
  expect(legalDocument("terminos", "0.1")).toBe(terms);
  expect(legalDocument("terminos")).toBe(terms);
  expect(legalDocument("terminos", "0.2")).toBeUndefined();
  expect(legalDocument("contrato")).toBeUndefined();
});
