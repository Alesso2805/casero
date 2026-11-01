import { Link, useParams } from "@tanstack/react-router";

import { formatDay } from "../landing/dates";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { textLink } from "./fields";

export function AccountDeletedPage() {
  const { purgeOn } = useParams({ from: "/cuenta-eliminada/$purgeOn" });
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.deleted.title}</h1>
      <p role="status">{text.deleted.body(formatDay(purgeOn))}</p>
      <Link to="/" className={textLink}>
        {text.deleted.home}
      </Link>
      <PublicFooter />
    </div>
  );
}
