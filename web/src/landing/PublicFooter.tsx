import { Link } from "@tanstack/react-router";

import { copy } from "./copy";
import complaintsNotice from "./libro-de-reclamaciones.png";

export function PublicFooter() {
  return (
    <footer className="flex flex-col gap-2 border-t border-stone-300 pt-6 text-base print:hidden">
      <Link to="/libro-de-reclamaciones" className="self-start">
        <img src={complaintsNotice} alt={copy.footer.complaints} width={160} height={124} />
      </Link>
      <Link to="/privacidad" className="inline-flex min-h-11 items-center self-start text-brand underline">
        {copy.footer.privacy}
      </Link>
      <p>{copy.footer.disclaimer}</p>
    </footer>
  );
}
