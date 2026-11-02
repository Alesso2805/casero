import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useLocation } from "@tanstack/react-router";

import { accountCopy as text } from "./copy";
import { fetchLegalStatus, isBlocked } from "./LegalGate";
import { useLogOut } from "./session";

type Section = "home" | "leases" | "declarations" | "more";

const TABS = [
  { section: "home", to: "/app", label: text.nav.home },
  { section: "leases", to: "/app/contratos", label: text.nav.leases },
  { section: "declarations", to: "/app/impuestos", label: text.nav.declarations },
  { section: "more", to: "/app/mas", label: text.nav.more },
] as const;

const SIDE_LINKS = [
  { to: "/app", label: text.home.greeting },
  { to: "/app/inmuebles", label: text.home.properties },
  { to: "/app/contratos", label: text.home.leases },
  { to: "/app/impuestos", label: text.home.declarations },
  { to: "/app/mensajes", label: text.home.templates },
  { to: "/app/plan", label: text.home.plan },
  { to: "/app/mis-datos", label: text.home.profile },
] as const;

function sectionOf(pathname: string): Section {
  const path = pathname.replace(/\/$/, "");
  if (path === "/app") {
    return "home";
  }
  if (path.startsWith("/app/contratos")) {
    return "leases";
  }
  return path.startsWith("/app/impuestos") ? "declarations" : "more";
}

function Tabs({ section }: { section: Section }) {
  return (
    <nav
      aria-label={text.nav.label}
      className="sticky bottom-0 z-10 grid grid-cols-4 bg-brand pb-[env(safe-area-inset-bottom)] text-white lg:hidden"
    >
      {TABS.map((tab) => (
        <Link
          key={tab.section}
          to={tab.to}
          activeOptions={{ exact: true }}
          aria-current={tab.section === section ? "page" : undefined}
          className={`flex min-h-15 items-center justify-center ${
            tab.section === section ? "border-2 border-brand bg-white font-bold text-brand" : ""
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

function SideMenu({ pathname }: { pathname: string }) {
  const logOut = useLogOut();
  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-4 bg-brand py-5 text-white lg:flex">
      <Link to="/" className="px-5 text-2xl font-bold tracking-tight">
        Casero
      </Link>
      <nav aria-label={text.nav.label} className="flex flex-col">
        {SIDE_LINKS.map((link) => {
          const current =
            link.to === "/app" ? pathname.replace(/\/$/, "") === "/app" : pathname.startsWith(link.to);
          return (
            <Link
              key={link.to}
              to={link.to}
              activeOptions={{ exact: true }}
              aria-current={current ? "page" : undefined}
              className={`flex min-h-12 items-center px-5 ${
                current ? "bg-white font-bold text-brand" : ""
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      <button
        type="button"
        disabled={logOut.isPending}
        className="mx-5 mt-auto min-h-12 border-2 border-white font-semibold disabled:opacity-60"
        onClick={() => {
          logOut.mutate(false);
        }}
      >
        {text.home.logOut}
      </button>
    </aside>
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  // Reads what the home page already asked for: a blocked account only sees that page's gate.
  const legal = useQuery({ queryKey: ["legal"], queryFn: fetchLegalStatus, enabled: false });
  const blocked = isBlocked(legal.data);
  return (
    <div className="flex min-h-dvh">
      {!blocked && <SideMenu pathname={pathname} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1">
          <Outlet />
        </div>
        {!blocked && <Tabs section={sectionOf(pathname)} />}
      </div>
    </div>
  );
}
