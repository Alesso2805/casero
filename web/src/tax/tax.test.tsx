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
    await userEvent.click(ana.getByRole("button", { name: "Copiar ruc del arrendador" }));
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
