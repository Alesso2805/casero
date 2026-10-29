import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";

const PATH = "/api/app/tax/declarations";
const ANA = {
  renter_id: "0195a0b0-0000-7000-8000-000000000010",
  renter_name: "Ana Quispe",
  doc_type: "dni",
  doc_number: "45678912",
  incomplete: false,
  company_tenant: false,
  lease_ids: ["0195a0b0-0000-7000-8000-000000000020", "0195a0b0-0000-7000-8000-000000000021"],
  collected_cents: 55100,
  old_debt_cents: 0,
  base_cents: 55100,
  tax_cents: 2800,
  payments: [] as unknown[],
  paid_cents: 0,
  pending_cents: 2800,
  after_declaring: null as unknown,
};
const ROSA = {
  ...ANA,
  renter_id: "0195a0b0-0000-7000-8000-000000000011",
  renter_name: "Rosa Huamán",
  doc_type: null,
  doc_number: null,
  incomplete: true,
  lease_ids: ["0195a0b0-0000-7000-8000-000000000022"],
  collected_cents: 30000,
  old_debt_cents: 120000,
  base_cents: 30000,
  tax_cents: 1500,
};
const ROSA_RENTER = {
  id: ROSA.renter_id,
  full_name: "Rosa Huamán",
  phone_e164: "+51987654321",
  doc_type: null,
  doc_last4: null,
};
const RENTERS = "/api/app/renters";
const SEPTEMBER = {
  period: "2026-09",
  ruc: "20131312955",
  due_on: "2026-10-21",
  due_status: "known",
  total_tax_cents: 2800,
  declarations: [ANA],
  untaxed: [],
  minimum_rent: [],
};

function card(name: string): HTMLElement {
  const item = screen.getByRole("heading", { name }).closest("li");
  if (!item) {
    throw new Error(`No card for ${name}`);
  }
  return item;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-27T15:00:00Z"));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Formularios de SUNAT", () => {
  test("opens on last month with one card per tenant, ready to copy", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const api = mockApi({ [PATH]: () => json(SEPTEMBER) });
    await renderPage("/app/impuestos");

    expect(await screen.findByText("Total del mes: S/ 28.00 en 1 Formulario 1683.")).toBeDefined();
    expect(new URL(api.requestsTo(PATH)[0]?.url ?? "").searchParams.get("period")).toBe("2026-09");
    expect(screen.getByText("Vencen el 21/10/2026, según el último dígito de tu RUC.")).toBeDefined();
    const ana = within(card("Ana Quispe"));
    expect(ana.getByText("setiembre de 2026")).toBeDefined();
    expect(ana.getByText("DNI")).toBeDefined();
    expect(ana.getByText("Predio")).toBeDefined();
    expect(ana.getByText("S/ 551.00")).toBeDefined();

    await userEvent.click(ana.getByRole("button", { name: "Copiar número de documento del inquilino" }));
    expect(await ana.findByText("Número de documento del inquilino copiado.")).toBeDefined();
    await userEvent.click(ana.getByRole("button", { name: "Copiar monto de la renta" }));
    await userEvent.click(ana.getByRole("button", { name: "Copiar RUC del arrendador" }));
    expect(writeText.mock.calls).toEqual([["45678912"], ["551"], ["20131312955"]]);
  });

  test("flags a tenant without a document, old debt, companies and cases it does not calculate", async () => {
    mockApi({
      [RENTERS]: () => json([ROSA_RENTER]),
      [PATH]: () =>
        json({
          ...SEPTEMBER,
          ruc: null,
          due_on: null,
          due_status: "no_ruc",
          total_tax_cents: 4300,
          declarations: [{ ...ANA, company_tenant: true }, ROSA],
          untaxed: [
            {
              lease_id: "0195a0b0-0000-7000-8000-000000000023",
              renter_name: "Luis Rojas",
              collected_cents: 30000,
            },
          ],
          minimum_rent: [
            { property_id: "0195a0b0-0000-7000-8000-000000000001", property_name: "Casa de Surco" },
          ],
        }),
    });
    await renderPage("/app/impuestos");

    expect(
      await screen.findByText("Total del mes: S/ 43.00 en 2 formularios 1683, uno por inquilino."),
    ).toBeDefined();
    expect(screen.getByText(/Registra tu RUC en Mis datos/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Ir a Mis datos" })).toBeDefined();
    expect(within(card("Ana Quispe")).getByText(/Tu inquilino es una empresa/)).toBeDefined();
    const rosa = within(card("Rosa Huamán"));
    expect(rosa.getByText(/Falta el documento de Rosa Huamán/)).toBeDefined();
    expect(rosa.getAllByText("Falta tu RUC")).toHaveLength(1);
    expect(rosa.queryByRole("button", { name: /Copiar número de documento/ })).toBeNull();
    expect(rosa.getByText(/Además cobraste S\/ 1,200.00 de deuda de 2025 o antes/)).toBeDefined();
    expect(screen.getByText("Luis Rojas: cobraste S/ 300.00.")).toBeDefined();
    expect(screen.getByText(/El alquiler de Casa de Surco está por debajo del mínimo/)).toBeDefined();
  });

  test("completes a tenant's document from the card", async () => {
    let saved = false;
    const api = mockApi({
      [RENTERS]: () => json([ROSA_RENTER]),
      [`${RENTERS}/${ROSA.renter_id}`]: () => {
        saved = true;
        return json({ ...ROSA_RENTER, doc_type: "ce", doc_last4: "4567" });
      },
      [PATH]: () =>
        json({
          ...SEPTEMBER,
          declarations: [
            saved ? { ...ROSA, doc_type: "ce", doc_number: "001234567", incomplete: false } : ROSA,
          ],
        }),
    });
    await renderPage("/app/impuestos");
    const rosa = within(await screen.findByRole("form", { name: "Completa el documento de Rosa Huamán" }));

    await userEvent.click(rosa.getByRole("button", { name: "Guardar documento" }));
    expect(await rosa.findByText("Escribe el número del documento.")).toBeDefined();
    await userEvent.selectOptions(rosa.getByLabelText("Tipo de documento"), "ce");
    await userEvent.type(rosa.getByLabelText("Número del documento"), " 001234567 ");
    await userEvent.click(rosa.getByRole("button", { name: "Guardar documento" }));

    expect(await within(card("Rosa Huamán")).findByText("001234567")).toBeDefined();
    expect(screen.queryByRole("form", { name: /Completa el documento/ })).toBeNull();
    const request = api.requestsTo(`${RENTERS}/${ROSA.renter_id}`)[0];
    expect(request?.method).toBe("PUT");
    expect(await request?.json()).toEqual({
      full_name: "Rosa Huamán",
      phone: "+51987654321",
      document: { doc_type: "ce", number: "001234567" },
    });
  });

  test("says when another tenant already has that document", async () => {
    mockApi({
      [RENTERS]: () => json([ROSA_RENTER]),
      [`${RENTERS}/${ROSA.renter_id}`]: () => json({ detail: "duplicate_document" }, 409),
      [PATH]: () => json({ ...SEPTEMBER, declarations: [ROSA] }),
    });
    await renderPage("/app/impuestos");
    const rosa = within(await screen.findByRole("form", { name: "Completa el documento de Rosa Huamán" }));

    await userEvent.type(rosa.getByLabelText("Número del documento"), "45678912");
    await userEvent.click(rosa.getByRole("button", { name: "Guardar documento" }));

    expect(await rosa.findByText(/Ya registraste a otro inquilino con ese documento/)).toBeDefined();
  });

  test("says when the schedule is not published and when nothing was collected", async () => {
    mockApi({
      [PATH]: (request) =>
        new URL(request.url).searchParams.get("period") === "2026-09"
          ? json({ ...SEPTEMBER, due_on: null, due_status: "unknown_schedule" })
          : json({ ...SEPTEMBER, period: "2026-10", declarations: [], total_tax_cents: 0 }),
    });
    await renderPage("/app/impuestos");

    expect(
      await screen.findByText("Fecha por confirmar: SUNAT todavía no publica el cronograma de 2026."),
    ).toBeDefined();
    expect(screen.getByRole("button", { name: "Mes siguiente" })).toHaveProperty("disabled", false);
    await userEvent.click(screen.getByRole("button", { name: "Mes siguiente" }));

    expect(
      await screen.findByText(
        "No registraste cobros en octubre de 2026, así que no hay formularios 1683 de ese mes.",
      ),
    ).toBeDefined();
    expect(screen.getByRole("button", { name: "Mes siguiente" })).toHaveProperty("disabled", true);
  });

  test("offers the year's files for the accountant", async () => {
    mockApi({ [PATH]: () => json(SEPTEMBER) });
    await renderPage("/app/impuestos");

    const payments = await screen.findByRole("link", { name: "Cobros de 2026 (CSV)" });
    expect(payments.getAttribute("href")).toBe("/api/app/exports/payments.csv?year=2026");
    expect(
      screen.getByRole("link", { name: "Formularios de 2026 (CSV)" }).getAttribute("href"),
    ).toBe("/api/app/exports/declarations.csv?year=2026");
  });

  test("explains that the free plan has no forms", async () => {
    mockApi({ [PATH]: () => json({ detail: "tax_module_unavailable" }, 403) });
    await renderPage("/app/impuestos");

    expect(await screen.findByText(/son parte del plan Casero/)).toBeDefined();
    expect(screen.getByText("Casero nunca te pide tu Clave SOL.")).toBeDefined();
  });

  test("sends a visitor without a session to log in", async () => {
    mockApi({ [PATH]: 401 });
    await renderPage("/app/impuestos");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });
});


describe("pagos a SUNAT", () => {
  const PAID = {
    id: "0195a0b0-0000-7000-8000-000000000050",
    amount_cents: 2800,
    paid_on: "2026-10-21",
    order_number: "1234567890",
  };

  test("records what the landlord paid SUNAT for a card", async () => {
    let paid = false;
    const api = mockApi({
      [PATH]: () =>
        json({
          ...SEPTEMBER,
          declarations: [
            paid ? { ...ANA, payments: [PAID], paid_cents: 2800, pending_cents: 0 } : ANA,
          ],
        }),
      "/api/app/tax/payments": () => {
        paid = true;
        return json({ ...PAID, period: "2026-09", renter_id: ANA.renter_id, base_cents: 55100, voided: false }, 201);
      },
    });
    await renderPage("/app/impuestos");
    await screen.findByText(/Total del mes/);

    const ana = within(card("Ana Quispe"));
    expect(ana.getByText("Falta pagar S/ 28.00")).toBeDefined();
    await userEvent.click(ana.getByRole("button", { name: "Registrar pago a SUNAT" }));
    expect(ana.getByLabelText("Monto pagado en soles")).toHaveProperty("value", "28");
    expect(ana.getByLabelText("Monto declarado (base)")).toHaveProperty("value", "551");
    await userEvent.clear(ana.getByLabelText("Monto declarado (base)"));
    await userEvent.type(ana.getByLabelText("Monto declarado (base)"), "500");
    await userEvent.type(ana.getByLabelText("Número de orden"), "1234567890");
    await userEvent.click(ana.getByRole("button", { name: "Guardar pago a SUNAT" }));

    expect(await screen.findByText("Listo, guardamos el pago a SUNAT.")).toBeDefined();
    expect(await screen.findByText("Pagaste S/ 28.00 el 21/10/2026 · orden 1234567890")).toBeDefined();
    expect(screen.getByText("Pagado")).toBeDefined();
    const body = (await api.requestsTo("/api/app/tax/payments")[0]?.json()) as Record<string, unknown>;
    expect(body).toEqual({
      id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-7/) as unknown,
      period: "2026-09",
      renter_id: ANA.renter_id,
      declared_base_cents: 50000,
      amount_cents: 2800,
      paid_on: "2026-10-27",
      order_number: "1234567890",
    });
  });

  test("explains a date SUNAT can't have taken", async () => {
    mockApi({
      [PATH]: () => json(SEPTEMBER),
      "/api/app/tax/payments": () => json({ detail: "paid_before_period" }, 422),
    });
    await renderPage("/app/impuestos");
    await screen.findByText(/Total del mes/);

    const ana = within(card("Ana Quispe"));
    await userEvent.click(ana.getByRole("button", { name: "Registrar pago a SUNAT" }));
    await userEvent.clear(ana.getByLabelText("Monto declarado (base)"));
    await userEvent.type(ana.getByLabelText("Número de orden"), "12-34");
    await userEvent.click(ana.getByRole("button", { name: "Guardar pago a SUNAT" }));
    expect(await ana.findByText("Escribe solo los números de la orden.")).toBeDefined();
    expect(ana.getByText("Escribe el monto declarado en soles, por ejemplo: 551.")).toBeDefined();
    await userEvent.type(ana.getByLabelText("Monto declarado (base)"), "551");
    await userEvent.clear(ana.getByLabelText("Número de orden"));
    await userEvent.type(ana.getByLabelText("Número de orden"), "1234");
    await userEvent.click(ana.getByRole("button", { name: "Guardar pago a SUNAT" }));

    expect(
      await ana.findByText("La fecha no puede ser anterior al mes que declaras."),
    ).toBeDefined();
  });

  test("voids a SUNAT payment with a reason", async () => {
    const voidPath = `/api/app/tax/payments/${PAID.id}/void`;
    const api = mockApi({
      [PATH]: () =>
        json({
          ...SEPTEMBER,
          declarations: [{ ...ANA, payments: [PAID], paid_cents: 2800, pending_cents: 0 }],
        }),
      [voidPath]: () =>
        json({ ...PAID, period: "2026-09", renter_id: ANA.renter_id, base_cents: 55100, voided: true }),
    });
    await renderPage("/app/impuestos");
    await screen.findByText(/Total del mes/);

    const ana = within(card("Ana Quispe"));
    await userEvent.click(ana.getByRole("button", { name: "Anular el pago de S/ 28.00" }));
    await userEvent.click(ana.getByRole("button", { name: "Sí, anular" }));
    expect(await ana.findByText("Escribe el motivo.")).toBeDefined();
    await userEvent.type(ana.getByLabelText("¿Por qué lo anulas?"), "Lo registré dos veces");
    await userEvent.click(ana.getByRole("button", { name: "Sí, anular" }));

    expect(await screen.findByText("Listo, anulamos el pago a SUNAT.")).toBeDefined();
    expect(await api.requestsTo(voidPath)[0]?.json()).toEqual({ reason: "Lo registré dos veces" });
  });

  test("tells what to do when a declaration changed after paying or is overdue", async () => {
    const after = (kind: string, base = 0, tax = 0) => ({
      kind,
      base_difference_cents: base,
      tax_difference_cents: tax,
    });
    const tenant = (n: number, name: string, change: unknown) => ({
      ...ANA,
      renter_id: `0195a0b0-0000-7000-8000-00000000006${String(n)}`,
      renter_name: name,
      after_declaring: change,
    });
    mockApi({
      [PATH]: () =>
        json({
          ...SEPTEMBER,
          declarations: [
            tenant(1, "Ana", after("up", 20000, 1000)),
            tenant(2, "Luis", after("down")),
            tenant(3, "Rosa", after("document_changed")),
            tenant(4, "Eva", after("overdue_unpaid")),
            tenant(5, "Juan", after("base_up", 50000, 2500)),
          ],
        }),
    });
    await renderPage("/app/impuestos");
    await screen.findByText(/Total del mes/);

    expect(
      await within(card("Ana")).findByText(
        "Cobraste S/ 200.00 más en setiembre de 2026 después de declarar. Presenta una declaración rectificatoria del 1683 con la nueva base y paga la diferencia de S/ 10.00 con intereses. Consúltalo con tu contador.",
      ),
    ).toBeDefined();
    expect(within(card("Luis")).getByText(/La base de setiembre de 2026 bajó/)).toBeDefined();
    expect(within(card("Rosa")).getByText(/Formulario 1693/)).toBeDefined();
    expect(within(card("Eva")).getByText(/Esta declaración venció el 21\/10\/2026/)).toBeDefined();
    expect(
      within(card("Juan")).getByText(
        "La base de setiembre de 2026 subió después de declarar. Presenta una rectificatoria del 1683 con la nueva base y paga la diferencia de S/ 25.00 con intereses. Consúltalo con tu contador.",
      ),
    ).toBeDefined();
  });
});
