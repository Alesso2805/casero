import { Link } from "@tanstack/react-router";

import policy from "../../../docs/legal/privacy-short.md?raw";
import { copy } from "./copy";
import { LegalArticle } from "./LegalArticle";
import { PublicFooter } from "./PublicFooter";
import { textLink } from "../account/fields";

export function PrivacyPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <Link to="/" className={textLink}>
        {copy.privacyBack}
      </Link>
      <LegalArticle source={policy} />
      <PublicFooter />
    </div>
  );
}
