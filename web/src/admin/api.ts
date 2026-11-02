import createClient from "openapi-fetch";

import type { components, paths } from "../api/admin-schema";
import { csrfMiddleware } from "../api/csrf";

export type Staff = components["schemas"]["StaffResponse"];
export type Account = components["schemas"]["AccountResponse"];

export const adminApi = createClient<paths>({
  baseUrl: globalThis.location.origin,
  fetch: (request) => globalThis.fetch(request),
});

adminApi.use(csrfMiddleware("/api/admin/csrf"));

export async function fetchStaff(): Promise<Staff | "login"> {
  const { data, response } = await adminApi.GET("/api/admin/me");
  if (data) {
    return data;
  }
  if (response.status === 401) {
    return "login";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}
