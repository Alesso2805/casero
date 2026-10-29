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
    expect(document.title).toBe("Mis contratos · Casero");
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

describe("lease page", () => {
  const STATEMENT_PATH = `/api/app/leases/${LEASE.id}/statement`;
  const PAYMENTS_PATH = `/api/app/leases/${LEASE.id}/payments`;
  const PAYMENT_ID = "0195a0b0-0000-7000-8000-000000000040";
  const VOID_PATH = `/api/app/payments/${PAYMENT_ID}/void`;
  const rent = {
    kind: "rent",
    pre_2026: null,
    corrects_charge_id: null,
    voided: false,
    partial: false,
    amount_cents: 80000,
  };
  const PAYMENT = {
    id: PAYMENT_ID,
    lease_id: LEASE.id,
    amount_cents: 170000,
    received_on: "2026-10-10",
    method: "yape",
    note: "Primera parte",
    voided: false,
  };
  const STATEMENT = {
    lease_id: LEASE.id,
    balance_cents: 110000,
    credit_cents: 0,
    up_to_date: false,
    charges: [
      {
        ...rent,
        id: "0195a0b0-0000-7000-8000-000000000030",
        kind: "opening_balance",
        period: null,
        pre_2026: true,
        amount_cents: 120000,
        due_date: "2025-12-31",
        outstanding_cents: 0,
        status: "paid",
      },
      {
        ...rent,
        id: "0195a0b0-0000-7000-8000-000000000031",
        period: "2026-09",
        due_date: "2026-09-05",
        outstanding_cents: 30000,
        status: "overdue",
        partial: true,
      },
      {
        ...rent,
        id: "0195a0b0-0000-7000-8000-000000000032",
        period: "2026-10",
        due_date: "2026-10-05",
        outstanding_cents: 0,
        status: null,
        voided: true,
      },
      {
        ...rent,
        id: "0195a0b0-0000-7000-8000-000000000033",
        kind: "rent_correction",
        corrects_charge_id: "0195a0b0-0000-7000-8000-000000000032",
        period: "2026-10",
        due_date: "2026-10-29",
        outstanding_cents: 80000,
        status: "due_soon",
      },
      {
        ...rent,
        id: "0195a0b0-0000-7000-8000-000000000034",
        kind: "adjustment",
        period: null,
        amount_cents: -5000,
        due_date: "2026-10-20",
        outstanding_cents: 0,
        status: null,
      },
    ],
    payments: [PAYMENT],
  };

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T15:00:00Z"));
    setCsrfCookie("csrf-token");
  });

  afterEach(() => {
    vi.useRealTimers();
    setCsrfCookie(null);
  });

  function mockLease(routes: Record<string, (request: Request) => Response> = {}) {
    return mockApi({
      "/api/app/leases": () => json([LEASE]),
      "/api/app/renters": () => json([RENTER]),
      "/api/app/properties": () => json([PROPERTY]),
      [STATEMENT_PATH]: () => json(STATEMENT),
      [`/api/app/leases/${LEASE.id}/tenant-link`]: () => json({ link: null }),
      ...routes,
    });
  }

  test("offers the WhatsApp reminder while a rent is unpaid", async () => {
    mockLease();
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(
      await screen.findByRole("button", { name: "Enviar por WhatsApp a Ana Quispe" }),
    ).toBeDefined();
    expect(screen.getByText(/Mejor entre las 8:00 y las 20:00/)).toBeDefined();
  });

  test("has no WhatsApp reminder once every rent is paid", async () => {
    mockLease({
      [STATEMENT_PATH]: () =>
        json({
          ...STATEMENT,
          balance_cents: 0,
          up_to_date: true,
          charges: STATEMENT.charges.map((line) =>
            line.status === null ? line : { ...line, outstanding_cents: 0, status: "paid" },
          ),
        }),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByRole("button", { name: "Registrar pago" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /Enviar por WhatsApp/ })).toBeNull();
  });

  test("opens from the lease card", async () => {
    mockLease();
    await renderPage("/app/contratos");

    await userEvent.click(await screen.findByRole("link", { name: "Ver cobros de Ana Quispe" }));

    expect(await screen.findByText("Te debe S/ 1,100.00")).toBeDefined();
  });

  test("shows what the renter owes, each charge's status and the payments", async () => {
    mockLease();
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByText("Te debe S/ 1,100.00")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Ana Quispe" })).toBeDefined();
    expect(screen.getByText("Cuarto 1 · Casa de Surco")).toBeDefined();
    expect(screen.getByText("Deuda de 2025 o antes")).toBeDefined();
    expect(screen.getByText("Pagado")).toBeDefined();
    expect(screen.getByText("Setiembre de 2026")).toBeDefined();
    expect(screen.getByText("Atrasado 52 días")).toBeDefined();
    expect(screen.getByText("Pagó S/ 500.00 de S/ 800.00")).toBeDefined();
    expect(screen.getByText("Octubre de 2026")).toBeDefined();
    expect(screen.getByText("Octubre de 2026 (corregido)")).toBeDefined();
    expect(screen.getByText("Anulado")).toBeDefined();
    expect(screen.getByText("Vence pronto: 29/10/2026")).toBeDefined();
    expect(screen.getByText("Descuento")).toBeDefined();
    expect(screen.getByText("S/ 50.00")).toBeDefined();
    expect(screen.getByText("Yape · Primera parte")).toBeDefined();
  });

  test("says when the renter has money in favor", async () => {
    mockLease({
      [STATEMENT_PATH]: () =>
        json({ ...STATEMENT, balance_cents: -2000, credit_cents: 2000, up_to_date: true }),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByText("Tiene S/ 20.00 a favor")).toBeDefined();
  });

  test("records a cash payment and warns about banking above the threshold", async () => {
    const api = mockLease({
      [PAYMENTS_PATH]: () =>
        json(
          {
            ...PAYMENT,
            id: "0195a0b0-0000-7000-8000-000000000041",
            amount_cents: 50050,
            received_on: "2026-10-27",
            method: "cash",
            note: null,
            bank_threshold_cents: 200000,
            before_control: false,
          },
          201,
        ),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Registrar pago" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Monto recibido en soles"));
    await userEvent.type(screen.getByLabelText("Monto recibido en soles"), "500.50");
    await userEvent.selectOptions(screen.getByLabelText("¿Cómo te pagó?"), "Efectivo");
    await userEvent.click(screen.getByRole("button", { name: "Guardar pago" }));

    const saved = await screen.findByText("Listo, guardamos el pago.");
    expect(document.activeElement).toBe(saved.parentElement);
    expect(screen.getByText(/Para alquileres desde S\/ 2,000.00 la ley exige/)).toBeDefined();
    expect(screen.queryByText(/anterior al mes desde el que llevas el control/)).toBeNull();
    const [request] = api.requestsTo(PAYMENTS_PATH);
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    const body = (await request?.json()) as Record<string, unknown>;
    expect(body.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
    expect({ ...body, id: "generated" }).toEqual({
      id: "generated",
      amount_cents: 50050,
      received_on: "2026-10-27",
      method: "cash",
      note: null,
    });
    await vi.waitFor(() => {
      expect(api.requestsTo(STATEMENT_PATH)).toHaveLength(2);
    });
  });

  test("asks how the renter paid and shows a refused date on its field", async () => {
    const api = mockLease({
      [PAYMENTS_PATH]: () => json({ detail: "received_before_2026" }, 422),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Registrar pago" }));
    await userEvent.type(screen.getByLabelText("Monto recibido en soles"), "800");
    await userEvent.click(screen.getByRole("button", { name: "Guardar pago" }));

    expect(await screen.findByText("Completa este dato.")).toBeDefined();
    expect(api.requestsTo(PAYMENTS_PATH)).toHaveLength(0);
    await userEvent.selectOptions(screen.getByLabelText("¿Cómo te pagó?"), "Yape");
    fireEvent.change(screen.getByLabelText(/Fecha en que recibiste el dinero/), {
      target: { value: "2025-12-31" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Guardar pago" }));

    expect(await screen.findByText(/no puede ser anterior al 1 de enero de 2026/)).toBeDefined();
    expect(screen.queryByText("Listo, guardamos el pago.")).toBeNull();
  });

  async function fillPayment(amount = "800") {
    await userEvent.type(screen.getByLabelText("Monto recibido en soles"), amount);
    await userEvent.selectOptions(screen.getByLabelText("¿Cómo te pagó?"), "Yape");
    await userEvent.click(screen.getByRole("button", { name: "Guardar pago" }));
  }

  async function sentIds(requests: Request[]) {
    return Promise.all(
      requests.map(async (request) => ((await request.json()) as { id: string }).id),
    );
  }

  const SAVED = { ...PAYMENT, amount_cents: 80000, note: null, bank_threshold_cents: null };

  test("warns when the payment was collected before the control month", async () => {
    mockLease({ [PAYMENTS_PATH]: () => json({ ...SAVED, before_control: true }, 201) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Registrar pago" }));
    await fillPayment();

    expect(await screen.findByText(/anterior al mes desde el que llevas el control/)).toBeDefined();
  });

  test("a lost response keeps the payment's id when the form is opened again", async () => {
    let calls = 0;
    const api = mockLease({
      [PAYMENTS_PATH]: () => {
        calls += 1;
        if (calls === 1) {
          throw new TypeError("Failed to fetch");
        }
        return json({ ...SAVED, before_control: false });
      },
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Registrar pago" }));
    await fillPayment();
    expect(await screen.findByText(/Algo salió mal/)).toBeDefined();
    await vi.waitFor(() => {
      expect(api.requestsTo(STATEMENT_PATH)).toHaveLength(2);
    });
    await userEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await userEvent.click(screen.getByRole("button", { name: "Registrar pago" }));
    await fillPayment();

    expect(await screen.findByText("Listo, guardamos el pago.")).toBeDefined();
    const [first, second] = await sentIds(api.requestsTo(PAYMENTS_PATH));
    expect(second).toBe(first);
  });

  test("a payment already saved with other data asks to check the list", async () => {
    let calls = 0;
    const api = mockLease({
      [PAYMENTS_PATH]: () => {
        calls += 1;
        return calls === 1
          ? json({ detail: "Conflict" }, 409)
          : json({ ...SAVED, before_control: false }, 201);
      },
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Registrar pago" }));
    await fillPayment();
    expect(await screen.findByText(/ya se había guardado con otros datos/)).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Guardar pago" }));

    expect(await screen.findByText("Listo, guardamos el pago.")).toBeDefined();
    const [first, second] = await sentIds(api.requestsTo(PAYMENTS_PATH));
    expect(second).not.toBe(first);
  });

  test("an expired session while saving goes to the login", async () => {
    mockLease({ [PAYMENTS_PATH]: () => new Response(null, { status: 401 }) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Registrar pago" }));
    await fillPayment();

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });

  test("voids a payment with its reason", async () => {
    const api = mockLease({ [VOID_PATH]: () => json({ ...PAYMENT, voided: true }) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Anular" }));
    const confirm = screen.getByRole("button", { name: "Anular pago" });
    expect(confirm).toHaveProperty("disabled", true);
    await userEvent.type(screen.getByLabelText("¿Por qué lo anulas?"), "Lo registré dos veces");
    await userEvent.click(confirm);

    await vi.waitFor(() => {
      expect(api.requestsTo(STATEMENT_PATH)).toHaveLength(2);
    });
    const [request] = api.requestsTo(VOID_PATH);
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(await request?.json()).toEqual({ reason: "Lo registré dos veces" });
  });

  test("says when the lease does not exist", async () => {
    mockLease({ [STATEMENT_PATH]: () => json({ detail: "lease_not_found" }, 404) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByText(/No encontramos este contrato/)).toBeDefined();
  });

  test("voids a charge with its reason", async () => {
    const charge = "0195a0b0-0000-7000-8000-000000000031";
    const api = mockLease({ [`/api/app/charges/${charge}/void`]: () => json({ id: charge }) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Anular Setiembre de 2026" }));
    await userEvent.type(screen.getByLabelText("¿Por qué lo anulas?"), "El monto estaba mal");
    await userEvent.click(screen.getByRole("button", { name: "Anular cobro" }));

    await vi.waitFor(() => {
      expect(api.requestsTo(STATEMENT_PATH)).toHaveLength(2);
    });
    const [request] = api.requestsTo(`/api/app/charges/${charge}/void`);
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(await request?.json()).toEqual({ reason: "El monto estaba mal" });
  });

  test("corrects a voided rent only until it has its correction", async () => {
    const voided = "0195a0b0-0000-7000-8000-000000000032";
    const corrections = `/api/app/leases/${LEASE.id}/charges/corrections`;
    const withoutCorrection = {
      ...STATEMENT,
      charges: STATEMENT.charges.filter((charge) => charge.kind !== "rent_correction"),
    };
    const api = mockLease({
      [STATEMENT_PATH]: () => json(withoutCorrection),
      [corrections]: () => json({ id: "x" }, 201),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(
      await screen.findByRole("button", { name: "Corregir el monto de Octubre de 2026" }),
    );
    await userEvent.type(screen.getByLabelText("Monto correcto en soles"), "750");
    await userEvent.click(screen.getByRole("button", { name: "Guardar corrección" }));

    await vi.waitFor(() => {
      expect(api.requestsTo(corrections)).toHaveLength(1);
    });
    const body = (await api.requestsTo(corrections)[0]?.json()) as Record<string, unknown>;
    expect(body.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
    expect({ ...body, id: "generated" }).toEqual({
      id: "generated",
      corrects_charge_id: voided,
      amount_cents: 75000,
    });
  });

  test("a rent that already has its correction offers no other", async () => {
    mockLease();
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByText("Octubre de 2026 (corregido)")).toBeDefined();
    expect(screen.queryByRole("button", { name: /Corregir el monto/ })).toBeNull();
  });

  test("records a discount as a credit", async () => {
    const adjustments = `/api/app/leases/${LEASE.id}/charges/adjustments`;
    const api = mockLease({ [adjustments]: () => json({ id: "x" }, 201) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Agregar cargo o descuento" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Monto en soles"));
    await userEvent.click(screen.getByLabelText("Un descuento"));
    await userEvent.type(screen.getByLabelText("Monto en soles"), "50");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Listo, guardamos el cargo o descuento.")).toBeDefined();
    const body = (await api.requestsTo(adjustments)[0]?.json()) as Record<string, unknown>;
    expect(body.amount_cents).toBe(-5000);
  });

  async function bodyOf(api: ReturnType<typeof mockApi>, path: string) {
    await vi.waitFor(() => {
      expect(api.requestsTo(path)).toHaveLength(1);
    });
    return (await api.requestsTo(path)[0]?.json()) as Record<string, unknown>;
  }

  const LEASE_PATH = `/api/app/leases/${LEASE.id}`;
  const updatedLease = () => json(LEASE);

  test("changes the rent from the next month not yet charged", async () => {
    const api = mockLease({ [`${LEASE_PATH}/rent-changes`]: () => json({ id: "x" }, 201) });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Cambiar el alquiler" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Nuevo alquiler mensual en soles"));
    await userEvent.type(screen.getByLabelText("Nuevo alquiler mensual en soles"), "900");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText(/Listo, guardamos el nuevo alquiler/)).toBeDefined();
    const body = await bodyOf(api, `${LEASE_PATH}/rent-changes`);
    expect(body.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
    expect(body.monthly_rent_cents).toBe(90000);
  });

  test("leaves the lease without a planned end", async () => {
    const api = mockLease({ [`${LEASE_PATH}/end-date`]: updatedLease });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Cambiar la fecha de fin" }));
    expect(screen.getByLabelText<HTMLInputElement>("Nueva fecha de fin").value).toBe("2026-11-10");
    fireEvent.change(screen.getByLabelText("Nueva fecha de fin"), { target: { value: "" } });
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Listo, actualizamos la fecha de fin.")).toBeDefined();
    expect(await bodyOf(api, `${LEASE_PATH}/end-date`)).toEqual({ end_date: null });
  });

  test("ends the lease with a discount for the days not used", async () => {
    const api = mockLease({ [`${LEASE_PATH}/termination`]: updatedLease });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Terminar el contrato" }));
    expect(screen.getByLabelText<HTMLInputElement>(/Fecha en que terminó/).value).toBe(
      "2026-10-27",
    );
    fireEvent.change(screen.getByLabelText(/Fecha en que terminó/), {
      target: { value: "2026-10-20" },
    });
    await userEvent.type(screen.getByLabelText(/Descuento por los días que no usó/), "100");
    await userEvent.click(screen.getByRole("button", { name: "Terminar contrato" }));

    expect(await screen.findByText("Listo, el contrato quedó terminado.")).toBeDefined();
    const body = await bodyOf(api, `${LEASE_PATH}/termination`);
    expect(body.ended_on).toBe("2026-10-20");
    const credit = body.credit as { id: string; amount_cents: number };
    expect(credit.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7/);
    expect(credit.amount_cents).toBe(10000);
  });

  test("explains why an end date is refused", async () => {
    mockLease({
      [`${LEASE_PATH}/termination`]: () => json({ detail: "end_before_control" }, 422),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Terminar el contrato" }));
    await userEvent.click(screen.getByRole("button", { name: "Terminar contrato" }));

    expect(await screen.findByText(/anterior al mes desde el que llevas el control/)).toBeDefined();
  });

  test("records the 2026 prior debt, the only era left", async () => {
    const api = mockLease({
      [`${LEASE_PATH}/charges/prior-debts`]: () => json({ id: "x" }, 201),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(
      await screen.findByRole("button", { name: "Registrar una deuda anterior" }),
    );
    expect(screen.getByText("Deuda de 2026, antes del mes de control")).toBeDefined();
    await userEvent.type(screen.getByLabelText(/Monto en soles/), "350");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    const body = await bodyOf(api, `${LEASE_PATH}/charges/prior-debts`);
    expect([body.pre_2026, body.amount_cents]).toEqual([false, 35000]);
  });

  test("an ended lease with money in favor shows what to return and records it", async () => {
    const adjustments = `${LEASE_PATH}/charges/adjustments`;
    const api = mockLease({
      "/api/app/leases": () => json([{ ...LEASE, ended_at: "2026-09-30" }]),
      [STATEMENT_PATH]: () =>
        json({ ...STATEMENT, balance_cents: -2000, credit_cents: 2000, up_to_date: true }),
      [adjustments]: () => json({ id: "x" }, 201),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByText("A devolver al inquilino: S/ 20.00")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Terminar el contrato" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Registrar devolución" }));

    expect(await screen.findByText("Listo, registramos la devolución.")).toBeDefined();
    expect((await bodyOf(api, adjustments)).amount_cents).toBe(2000);
  });

  const LINK_PATH = `/api/app/leases/${LEASE.id}/tenant-link`;
  const LINK = {
    url: "https://casero.example/i#t=AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI",
    created_at: "2026-10-27T15:00:00Z",
    last_used_at: null,
  };

  test("creates the tenant's link and copies it", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    mockLease({
      [LINK_PATH]: (request) => json(request.method === "POST" ? LINK : { link: null }, 201),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Crear enlace" }));

    expect(await screen.findByDisplayValue(LINK.url)).toBeDefined();
    expect(screen.getByText("Todavía no lo ha abierto.")).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Copiar enlace" }));
    expect(await screen.findByText(/Enlace copiado/)).toBeDefined();
    expect(writeText).toHaveBeenCalledWith(LINK.url);
  });

  test("shows when the tenant last opened the link and revokes it", async () => {
    const api = mockLease({
      [LINK_PATH]: () => json({ link: { ...LINK, last_used_at: "2026-10-26T20:00:00Z" } }),
      [`${LINK_PATH}/revoke`]: () => json({ link: null }),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByText("Lo abrió por última vez el 26/10/2026.")).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Desactivar el enlace" }));

    expect(await screen.findByText("Listo, el enlace ya no funciona.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Crear enlace" })).toBeDefined();
    expect(api.requestsTo(`${LINK_PATH}/revoke`)[0]?.headers.get("X-CSRF-Token")).toBe(
      "csrf-token",
    );
  });

  test("explains when the plan has no tenant portal", async () => {
    mockLease({
      [LINK_PATH]: (request) =>
        request.method === "POST"
          ? json({ detail: "portal_unavailable" }, 403)
          : json({ link: null }),
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Crear enlace" }));

    expect(await screen.findByText(/Tu plan no incluye el portal del inquilino/)).toBeDefined();
  });

  test("sends visitors without a session to log in", async () => {
    mockApi({
      "/api/app/leases": 401,
      "/api/app/renters": 401,
      "/api/app/properties": 401,
      [STATEMENT_PATH]: 401,
    });
    await renderPage(`/app/contratos/${LEASE.id}`);

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });
});
