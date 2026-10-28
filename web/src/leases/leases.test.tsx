import { cleanup, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";
import { controlPeriods, uuidv7 } from "./terms";

function setCsrfCookie(value: string | null) {
  // __Host- cookies must be Secure with Path=/, or the browser (and jsdom) drops them.
  document.cookie = value
    ? `__Host-casero_csrf=${value}; Path=/; Secure`
    : "__Host-casero_csrf=; Path=/; Secure; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

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
    expect(screen.getByRole("link", { name: "Nuevo contrato" })).toHaveProperty(
      "pathname",
      "/app/contratos/nuevo",
    );
  });

  test("sends visitors without a session to log in", async () => {
    mockApi({ "/api/app/leases": 401, "/api/app/renters": 401, "/api/app/properties": 401 });
    await renderPage("/app/contratos");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });
});

describe("lease terms", () => {
  test("uuid v7 carries its version, variant and time order", () => {
    const first = uuidv7(Date.UTC(2026, 9, 27));
    const second = uuidv7(Date.UTC(2026, 9, 28));

    expect(first).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(first < second).toBe(true);
  });

  test("control months go from the start, never before 2026, to the current month", () => {
    expect(controlPeriods("2025-06-01", "2026-03-15")).toEqual(["2026-01", "2026-02", "2026-03"]);
    expect(controlPeriods("2026-02-10", "2026-03-15")).toEqual(["2026-02", "2026-03"]);
    expect(controlPeriods("2026-05-01", "2026-03-15")).toEqual(["2026-05"]);
    expect(controlPeriods("", "2026-03-15")).toEqual(["2026-03"]);
  });
});

describe("new lease", () => {
  const RENTER_CREATED = { ...RENTER, id: "0195a0b0-0000-7000-8000-000000000011" };

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T15:00:00Z"));
    setCsrfCookie("csrf-token");
  });

  afterEach(() => {
    vi.useRealTimers();
    setCsrfCookie(null);
  });

  function mockForm(overrides: Record<string, (request: Request) => Response> = {}) {
    return mockApi({
      "/api/app/properties": () => json([PROPERTY]),
      "/api/app/renters": (request) =>
        request.method === "POST" ? json(RENTER_CREATED, 201) : json([RENTER]),
      "/api/app/leases": (request) => (request.method === "POST" ? json(LEASE, 201) : json([])),
      ...overrides,
    });
  }

  test("registers a new renter and the lease with its prior debts", async () => {
    const api = mockForm();
    await renderPage("/app/contratos/nuevo");

    await userEvent.selectOptions(await screen.findByLabelText("¿Qué unidad alquilas?"), "Cochera");
    await userEvent.click(screen.getByLabelText("A un inquilino nuevo"));
    await userEvent.type(screen.getByLabelText("Nombre completo del inquilino"), "Luis Rojas");
    await userEvent.type(screen.getByLabelText("Celular (opcional)"), "912 345 678");
    await userEvent.selectOptions(screen.getByLabelText("Documento (opcional)"), "dni");
    await userEvent.type(screen.getByLabelText("Número del documento"), "45678912");
    await userEvent.type(screen.getByLabelText("Alquiler mensual en soles"), "800");
    await userEvent.type(screen.getByLabelText("¿Qué día del mes te paga?"), "5");
    fireEvent.change(screen.getByLabelText("Fecha de inicio del contrato"), {
      target: { value: "2025-06-01" },
    });
    await userEvent.selectOptions(
      screen.getByLabelText("¿Desde qué mes llevas el control en Casero?"),
      "2026-09",
    );
    await userEvent.type(
      screen.getByLabelText("Deuda de 2025 o antes, en soles (opcional)"),
      "1200",
    );
    await userEvent.type(
      screen.getByLabelText("Deuda de 2026 antes del mes de control, en soles (opcional)"),
      "500.50",
    );
    await userEvent.click(screen.getByRole("button", { name: "Guardar contrato" }));

    expect(await screen.findByRole("heading", { name: "Mis contratos" })).toBeDefined();
    const [renter] = api.requestsTo("/api/app/renters").filter((r) => r.method === "POST");
    expect(await renter?.json()).toEqual({
      full_name: "Luis Rojas",
      phone: "912 345 678",
      document: { doc_type: "dni", number: "45678912" },
    });
    const [lease] = api.requestsTo("/api/app/leases").filter((r) => r.method === "POST");
    expect(lease?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    const body = (await lease?.json()) as Record<string, unknown>;
    expect(body.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
    expect({ ...body, id: "generated" }).toEqual({
      id: "generated",
      unit_id: "0195a0b0-0000-7000-8000-000000000003",
      renter_id: RENTER_CREATED.id,
      monthly_rent_cents: 80000,
      due_day: 5,
      start_date: "2025-06-01",
      end_date: null,
      control_from_period: "2026-09",
      tax_treatment: "standard",
      opening_balance_pre_2026_cents: 120000,
      opening_balance_2026_cents: 50050,
    });
  });

  test("shows the server's refusals on their fields and keeps the created renter", async () => {
    let leaseCalls = 0;
    const api = mockForm({
      "/api/app/leases": (request) => {
        if (request.method !== "POST") {
          return json([]);
        }
        leaseCalls += 1;
        return json({ detail: "unit_occupied" }, 409);
      },
    });
    await renderPage("/app/contratos/nuevo");

    await userEvent.selectOptions(
      await screen.findByLabelText("¿Qué unidad alquilas?"),
      "Cuarto 1",
    );
    await userEvent.click(screen.getByLabelText("A un inquilino nuevo"));
    await userEvent.type(screen.getByLabelText("Nombre completo del inquilino"), "Luis Rojas");
    await userEvent.type(screen.getByLabelText("Alquiler mensual en soles"), "800");
    await userEvent.type(screen.getByLabelText("¿Qué día del mes te paga?"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Guardar contrato" }));

    expect(await screen.findByText("Esa unidad ya tiene un contrato activo.")).toBeDefined();
    expect(screen.getByLabelText("A un inquilino que ya registré")).toHaveProperty(
      "checked",
      true,
    );
    await userEvent.click(screen.getByRole("button", { name: "Guardar contrato" }));

    await vi.waitFor(() => {
      expect(leaseCalls).toBe(2);
    });
    expect(api.requestsTo("/api/app/renters").filter((r) => r.method === "POST")).toHaveLength(1);
  });

  test("explains a split conjugal property and a fixed control month", async () => {
    mockForm({
      "/api/app/properties": () => json([{ ...PROPERTY, ownership: "conjugal_split" }]),
    });
    await renderPage("/app/contratos/nuevo");

    await userEvent.selectOptions(
      await screen.findByLabelText("¿Qué unidad alquilas?"),
      "Cuarto 1",
    );
    fireEvent.change(screen.getByLabelText("Fecha de inicio del contrato"), {
      target: { value: "2026-12-01" },
    });

    expect(screen.getByText(/cada uno declara su mitad/)).toBeDefined();
    expect(screen.queryByLabelText("Una persona")).toBeNull();
    expect(
      screen.getByText("El control empieza en diciembre de 2026, el mes de inicio."),
    ).toBeDefined();
  });

  test("asks for a free unit first", async () => {
    const both = [LEASE, { ...LEASE, unit_id: "0195a0b0-0000-7000-8000-000000000003" }];
    mockForm({ "/api/app/leases": () => json(both) });
    await renderPage("/app/contratos/nuevo");

    expect(await screen.findByText(/No tienes unidades libres/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Registrar un inmueble" })).toBeDefined();
  });
});
