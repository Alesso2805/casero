import { useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { components } from "./schema";

export type Business = components["schemas"]["BusinessResponse"];

async function fetchBusiness(): Promise<Business> {
  const { data } = await api.GET("/api/public/business");
  if (!data) {
    throw new Error("The business identity is unavailable");
  }
  return data;
}

export function useBusiness() {
  return useQuery({ queryKey: ["business"], queryFn: fetchBusiness, staleTime: Infinity });
}
