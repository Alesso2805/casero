import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../../test/api";
import { renderPage } from "../../test/render";
import { formatPercent } from "./CalculatorPage";

const CALCULATOR = "/api/public/tax-calculator";
const RESULT = {
  period: "2026-03",
  rate_bp: 625,
  deduction_bp: 2000,
  lines: [
    { collected_cents: 55100, base_cents: 55100, tax_cents: 2800 },
    { collected_cents: 54950, base_cents: 55000, tax_cents: 2800 },
  ],
  total_tax_cents: 5600,
  due_on: "2026-04-17",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fill(amounts: string[], ruc: string) {
  await userEvent.selectOptions(await screen.findByLabelText("Mes en que cobraste"), "3");
  await userEvent.selectOptions(screen.getByLabelText("Año"), "2026");
  for (const [index, amount] of amounts.entries()) {
    if (index > 0) {
      await userEvent.click(screen.getByRole("button", { name: "Agregar otro inquilino" }));
    }
    await userEvent.type(screen.getByLabelText(`Inquilino ${String(index + 1)} (S/)`), amount);
  }
  await userEvent.selectOptions(screen.getByLabelText(/Último dígito de tu RUC/), ruc);
}

describe("tax calculator", () => {
  test.each([
    [625, 10_000, "6.25"],
    [8000, 10_000, "80"],
    [625 * 8000, 10_000 * 10_000, "5"],
    [650, 10_000, "6.5"],
  ])("formats %i/%i as %s %%", (numerator, denominator, percent) => {
    expect(formatPercent(numerator, denominator)).toBe(percent);
  });

  test("computes one payment per renter with the due date", async () => {
    const api = mockApi({ [CALCULATOR]: () => json(RESULT) });
    await renderPage("/calculadora");

    await fill(["551", "549.50"], "3");
    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    expect(
      await screen.findByText("Total del mes: S/ 56.00 en 2 formularios 1683, uno por inquilino."),
    ).toBeDefined();
    expect(screen.getByText("Vence el 17/04/2026, según el último dígito de tu RUC.")).toBeDefined();
    expect(
      screen.getByText(
        "Se paga el 5 % de lo que cobras: 6.25 % sobre el 80 % de lo cobrado, redondeado a soles enteros.",
      ),
    ).toBeDefined();
    const [request] = api.requestsTo(CALCULATOR);
    expect(await request?.json()).toEqual({
      period: "2026-03",
      collected_cents: [55100, 54950],
      ruc_group: "2-3",
    });
  });

  test("asks for the RUC digit to show the due date", async () => {
    mockApi({ [CALCULATOR]: () => json({ ...RESULT, due_on: null }) });
    await renderPage("/calculadora");

    await fill(["551"], "");
    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    expect(
      await screen.findByText("Indica el último dígito de tu RUC para ver la fecha límite."),
    ).toBeDefined();
  });

  test("explains a year without rules", async () => {
    mockApi({ [CALCULATOR]: 404 });
    await renderPage("/calculadora");

    await fill(["551"], "bc");
    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Todavía no tenemos las reglas de 2026. Elige otro mes.",
    );
  });

  test("asks for amounts in soles before calling the API", async () => {
    const api = mockApi({ [CALCULATOR]: () => json(RESULT) });
    await renderPage("/calculadora");

    await fill(["ochocientos"], "");
    await userEvent.click(screen.getByRole("button", { name: "Calcular" }));

    expect(
      await screen.findByText("Escribe el monto en soles, por ejemplo: 850 o 850.50."),
    ).toBeDefined();
    expect(api.requestsTo(CALCULATOR)).toEqual([]);
  });

  test("joins the waitlist as coming from the calculator", async () => {
    const api = mockApi({ "/api/public/waitlist": 202 });
    await renderPage("/calculadora");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    await screen.findByText("¡Listo! Te escribiremos a este correo cuando abramos.");
    const [request] = api.requestsTo("/api/public/waitlist");
    expect(await request?.json()).toMatchObject({ source: "calculator" });
  });
});
