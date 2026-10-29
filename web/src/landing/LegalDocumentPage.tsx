import { Link, useParams } from "@tanstack/react-router";

import { copy } from "./copy";
import { LegalArticle } from "./LegalArticle";
import { legalDocument } from "./legalDocuments";
import { PublicFooter } from "./PublicFooter";
import { textLink } from "../account/fields";

export function LegalDocumentPage() {
  const { document, version } = useParams({ strict: false });
  const source = document ? legalDocument(document, version) : undefined;
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <Link to="/" className={textLink}>
        {copy.privacyBack}
      </Link>
      {source ? <LegalArticle source={source} /> : <p role="alert">{copy.legalNotFound}</p>}
      <PublicFooter />
    </div>
  );
}
