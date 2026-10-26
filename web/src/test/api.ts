import { vi } from "vitest";

type Route = number | ((request: Request) => Response);

export const testBusiness = {
  name: "Negocio de Prueba",
  ruc: "10000000001",
  address: "Av. Ficticia 100, Lima",
  complaints_inbox: "reclamos@example.com",
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function mockApi(routes: Record<string, Route>) {
  const requests: Request[] = [];
  const allRoutes: Record<string, Route> = {
    "/api/public/business": () => json(testBusiness),
    ...routes,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => {
      requests.push(request);
      const route = allRoutes[new URL(request.url).pathname];
      if (route === undefined) {
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
