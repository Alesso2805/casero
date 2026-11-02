import { Link } from "@tanstack/react-router";

import { accountCopy as text } from "./copy";
import { LogOutButtons } from "./session";

const LINKS = [
  { to: "/app/inmuebles", label: text.home.properties },
  { to: "/app/mensajes", label: text.home.templates },
  { to: "/app/plan", label: text.home.plan },
  { to: "/app/mis-datos", label: text.home.profile },
] as const;

export function MorePage() {
  return (
    <div className="flex flex-col text-base">
      <header className="grid-paper px-4 pt-5 pb-4">
        <h1 className="w-max bg-white text-3xl font-bold tracking-tight text-brand">{text.nav.more}</h1>
      </header>
      <nav aria-label={text.nav.more} className="flex flex-col border-t-2 border-brand">
        {LINKS.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className="flex min-h-15 items-center border-b border-rule px-4 text-lg font-semibold text-brand"
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="px-4 py-5">
        <LogOutButtons />
      </div>
    </div>
  );
}
