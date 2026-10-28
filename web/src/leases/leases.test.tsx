import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";

const PROPERTY = {
  id: "0195a0b0-0000-7000-8000-000000000001",
  name: "Casa de Surco",
  address_line: null,
  district: "Surco",
  ownership: "sole",
  autovaluo_cents: null,
  rented_share_pct: 100,
  archived: false,
  units: [
    {
      id: "0195a0b0-0000-7000-8000-000000000002",
      property_id: "0195a0b0-0000-7000-8000-000000000001",
      name: "Cuarto 1",
      kind: "room",
      archived: false,
    },
    {
      id: "0195a0b0-0000-7000-8000-000000000003",
      property_id: "0195a0b0-0000-7000-8000-000000000001",
      name: "Cochera",
      kind: "parking",
      archived: false,
    },
  ],
};
const RENTER = {
  id: "0195a0b0-0000-7000-8000-000000000010",
  full_name: "Ana Quispe",
  phone_e164: "+51987654321",
  doc_type: "dni",
  doc_last4: "8912",
};
const LEASE = {
  id: "0195a0b0-0000-7000-8000-000000000020",
  unit_id: "0195a0b0-0000-7000-8000-000000000002",
  renter_id: RENTER.id,
  monthly_rent_cents: 80000,
  due_day: 5,
  start_date: "2025-06-01",
  end_date: "2026-11-10",
  ended_at: null,
  control_from_period: "2026-09",
  tax_treatment: "standard",
  days_to_end: 14,
  ending_soon: true,
};

function mockAccount(leases: unknown[]) {
  return mockApi({
    "/api/app/leases": () => json(leases),
    "/api/app/renters": () => json([RENTER]),
    "/api/app/properties": () => json([PROPERTY]),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("leases list", () => {
  test("shows each lease with its renter, unit, rent and end notice", async () => {
    mockAccount([LEASE]);
    await renderPage("/app/contratos");

    expect(await screen.findByRole("heading", { name: "Ana Quispe" })).toBeDefined();
    expect(screen.getByText("Cuarto 1 · Casa de Surco")).toBeDefined();
    expect(screen.getByText("S/ 800.00 al mes")).toBeDefined();
    expect(screen.getByText("Paga el día 5 de cada mes")).toBeDefined();
    expect(screen.getByText("Desde el 01/06/2025 · Hasta el 10/11/2026")).toBeDefined();
    expect(screen.getByText(/Termina en 14 días/)).toBeDefined();
  });

  test("keeps ended leases apart and marks the ones outside the tax module", async () => {
    mockAccount([
      { ...LEASE, ending_soon: false, days_to_end: 40, tax_treatment: "unsupported" },
      {
        ...LEASE,
        id: "0195a0b0-0000-7000-8000-000000000021",
        unit_id: "0195a0b0-0000-7000-8000-000000000003",
        ended_at: "2026-09-30",
        ending_soon: false,
        days_to_end: null,
      },
    ]);
    await renderPage("/app/contratos");

    expect(await screen.findByText(/no entra al cálculo/)).toBeDefined();
    expect(screen.queryByText(/Termina en/)).toBeNull();
    expect(screen.getByText("Terminados (1)")).toBeDefined();
  });

  test("invites a landlord without leases", async () => {
    mockAccount([]);
    await renderPage("/app/contratos");

    expect(await screen.findByText(/Todavía no registras contratos/)).toBeDefined();
  });

  test("sends visitors without a session to log in", async () => {
    mockApi({ "/api/app/leases": 401, "/api/app/renters": 401, "/api/app/properties": 401 });
    await renderPage("/app/contratos");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });
});
