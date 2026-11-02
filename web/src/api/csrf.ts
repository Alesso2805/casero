import type { Middleware } from "openapi-fetch";

const CSRF_COOKIE = "__Host-casero_csrf";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return cookie ? cookie.slice(prefix.length) : null;
}

async function csrfToken(issuePath: string): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) {
    return existing;
  }
  await globalThis.fetch(new Request(new URL(issuePath, globalThis.location.origin)));
  return readCookie(CSRF_COOKIE);
}

/** Double-submit CSRF (ADR-0004): every unsafe request echoes the cookie in a header. */
export function csrfMiddleware(issuePath: string): Middleware {
  return {
    async onRequest({ request }) {
      if (UNSAFE_METHODS.has(request.method)) {
        const token = await csrfToken(issuePath);
        if (token) {
          request.headers.set("X-CSRF-Token", token);
        }
      }
      return request;
    },
  };
}
