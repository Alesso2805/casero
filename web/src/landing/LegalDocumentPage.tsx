import { Link, useParams } from "@tanstack/react-router";

import privacy from "../../../docs/legal/privacy.md?raw";
import consent from "../../../docs/legal/sensitive-consent.md?raw";
import terms from "../../../docs/legal/terms.md?raw";
import { copy } from "./copy";
import { LegalArticle } from "./LegalArticle";
import { PublicFooter } from "./PublicFooter";

// The paths match legal_documents.url; every version is 0.1 for now.
const DOCUMENTS: Record<string, string> = {
  terminos: terms,
  privacidad: privacy,
  "consentimiento-datos-sensibles": consent,
};

export function LegalDocumentPage() {
  const { document } = useParams({ strict: false });
  const source = document ? DOCUMENTS[document] : undefined;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <Link to="/" className="text-brand underline">
        {copy.privacyBack}
      </Link>
      {source ? <LegalArticle source={source} /> : <p role="alert">{copy.legalNotFound}</p>}
      <PublicFooter />
    </div>
  );
}
