import createClient from "openapi-fetch";

import type { paths } from "./schema";

const CSRF_COOKIE = "__Host-casero_csrf";
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return cookie ? cookie.slice(prefix.length) : null;
}

async function csrfToken(): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) {
    return existing;
  }
  await globalThis.fetch(new Request(new URL("/api/public/csrf", globalThis.location.origin)));
  return readCookie(CSRF_COOKIE);
}

export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  fetch: (request) => globalThis.fetch(request),
});

// Double-submit CSRF (ADR-0004): every unsafe request echoes the cookie in a header.
api.use({
  async onRequest({ request }) {
    if (UNSAFE_METHODS.has(request.method)) {
      const token = await csrfToken();
      if (token) {
        request.headers.set("X-CSRF-Token", token);
      }
    }
    return request;
  },
});
