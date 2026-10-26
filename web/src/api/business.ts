import { useQuery } from "@tanstack/react-query";

// Served by Caddy from the server's environment, not by the API (see infra/caddy).
export interface Business {
  name: string;
  ruc: string;
  address: string;
  complaints_inbox: string;
}

async function fetchBusiness(): Promise<Business> {
  const url = new URL("/api/public/business", globalThis.location.origin);
  const response = await globalThis.fetch(new Request(url));
  if (!response.ok) {
    throw new Error("The business identity is unavailable");
  }
  return (await response.json()) as Business;
}

export function useBusiness() {
  return useQuery({ queryKey: ["business"], queryFn: fetchBusiness, staleTime: Infinity });
}
