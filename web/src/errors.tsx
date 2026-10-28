import { Link } from "@tanstack/react-router";
import { useEffect } from "react";
import { textLink } from "./account/fields";

const MAX_REPORTS_PER_PAGE = 5;
const FRAME = /(https?:\/\/[^\s()]+|\/[^\s()]+):(\d+):(\d+)/;

export const errorsCopy = {
  failure: {
    title: "Algo salió mal",
    detail: "Recarga la página. Si sigue pasando, vuelve a intentarlo en unos minutos.",
    reload: "Recargar la página",
  },
  notFound: {
    title: "No encontramos esta página",
    detail: "Puede que el enlace esté incompleto o que la página ya no exista.",
    home: "Ir al inicio",
  },
} as const;

let reported = 0;

/** Where in the bundle it failed, as path:line:column, never the page's query or fragment. */
export function codeLocation(stack: string | undefined): string | undefined {
  const match = stack === undefined ? null : FRAME.exec(stack);
  if (match === null) {
    return undefined;
  }
  const [, script = "", line = "", column = ""] = match;
  const path = script.startsWith("/") ? script : new URL(script).pathname;
  return `${path.split(/[?#]/)[0] ?? ""}:${line}:${column}`;
}

/** Tells the server an error's type, route and code location; nothing a person typed (ADR-0011). */
export function reportError(error: unknown): void {
  if (reported >= MAX_REPORTS_PER_PAGE) {
    return;
  }
  reported += 1;
  const name = error instanceof Error ? error.name : "UnknownError";
  const where = error instanceof Error ? codeLocation(error.stack) : undefined;
  const request = new Request(new URL("/api/public/client-errors", window.location.origin), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, route: window.location.pathname, where }),
    keepalive: true,
  });
  void fetch(request).catch(() => undefined);
}

export function listenForErrors(): void {
  window.addEventListener("error", (event) => {
    reportError(event.error);
  });
  window.addEventListener("unhandledrejection", (event) => {
    reportError(event.reason);
  });
}

export function ErrorPage({ error }: { error: unknown }) {
  useEffect(() => {
    reportError(error);
  }, [error]);
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{errorsCopy.failure.title}</h1>
      <p>{errorsCopy.failure.detail}</p>
      <button
        type="button"
        className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white"
        onClick={() => {
          window.location.reload();
        }}
      >
        {errorsCopy.failure.reload}
      </button>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{errorsCopy.notFound.title}</h1>
      <p>{errorsCopy.notFound.detail}</p>
      <Link to="/" className={textLink}>
        {errorsCopy.notFound.home}
      </Link>
    </div>
  );
}
