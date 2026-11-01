import { api } from "../api/client";
import type { components } from "../api/schema";

export type Account = components["schemas"]["AccountResponse"];

export async function fetchAccount(): Promise<Account | "login" | "paused"> {
  const { data, response } = await api.GET("/api/app/account");
  if (data) {
    return data;
  }
  if (response.status === 401) {
    return "login";
  }
  if (response.status === 403) {
    return "paused";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}
