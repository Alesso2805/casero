import { vi } from "vitest";

type Route = number | ((request: Request) => Response);

export const testBusiness = {
  name: "Negocio de Prueba",
  ruc: "10000000001",
  address: "Av. Ficticia 100, Lima",
  yape: "999000111",
  complaints_inbox: "reclamos@example.com",
  privacy_inbox: "privacidad@example.com",
};

export const testAccount = {
  display_name: "Ana",
  plan_code: "casero",
  status: "trial",
  trial_ends_at: "2026-11-26",
  ends_at: "2026-11-26",
  grace_until: null,
  max_active_leases: 10,
  features: {},
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export const unmockedRequests: string[] = [];

export function mockApi(routes: Record<string, Route>) {
  const requests: Request[] = [];
  const allRoutes: Record<string, Route> = {
    "/api/public/business": () => json(testBusiness),
    "/api/public/csrf": 204,
    "/api/app/legal": () => json({ pending: [], consent_withdrawn: false }),
    "/api/app/lease-tools": () => json({ limit: 10, over_limit: false, leases: [] }),
    "/api/app/account": () => json(testAccount),
    ...routes,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      requests.push(request);
      const route = allRoutes[new URL(request.url).pathname];
      if (route === undefined) {
        unmockedRequests.push(`${request.method} ${new URL(request.url).pathname}`);
        return Promise.resolve(new Response(null, { status: 404 }));
      }
      return Promise.resolve(
        typeof route === "number" ? new Response(null, { status: route }) : route(request),
      );
    }),
  );
  return {
    requestsTo: (path: string) => requests.filter((request) => new URL(request.url).pathname === path),
  };
}
