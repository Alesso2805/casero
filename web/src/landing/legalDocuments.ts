import privacy from "../../../docs/legal/privacy.md?raw";
import consent from "../../../docs/legal/sensitive-consent.md?raw";
import terms from "../../../docs/legal/terms.md?raw";

// Paths and versions match legal_documents.url. When a document changes, the version people
// accepted moves to docs/legal/archive/ and stays listed here, so its link keeps its own text;
// the last version listed is the current one.
export const LEGAL_DOCUMENTS: Record<string, Record<string, string>> = {
  terminos: { "0.1": terms },
  privacidad: { "0.1": privacy },
  "consentimiento-datos-sensibles": { "0.1": consent },
};

export function legalDocument(document: string, version?: string): string | undefined {
  const versions = LEGAL_DOCUMENTS[document];
  if (!versions) {
    return undefined;
  }
  return version === undefined ? Object.values(versions).at(-1) : versions[version];
}
