import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi, testBusiness } from "../../test/api";
import { renderPage } from "../../test/render";
import { formatSoles, parseSolesToCents } from "../money";

const COMPLAINTS = "/api/public/complaints";
const FILED = { number: "000000001-2026", filed_at: "2026-10-23T15:05:00Z", due_on: "2026-11-13" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fillRequiredFields() {
  await userEvent.type(await screen.findByLabelText("Nombre completo"), "Ana Quispe Mamani");
  await userEvent.type(screen.getByLabelText("Número de documento"), "1234 5678");
  await userEvent.type(screen.getByLabelText("Correo electrónico"), "ana@example.com");
  await userEvent.type(screen.getByLabelText("Detalle"), "Me cobraron dos veces la suscripción.");
}

describe("soles", () => {
  test.each([
    ["19", 1900],
    ["19.5", 1950],
    ["S/ 1500,25", 150025],
    ["0.05", 5],
    ["1,500", null],
    ["19.505", null],
    ["-3", null],
  ])("parses %s", (text, cents) => {
    expect(parseSolesToCents(text)).toBe(cents);
  });

  test("formats like the backend", () => {
    expect(formatSoles(275000)).toBe("S/ 2,750.00");
    expect(formatSoles(1905)).toBe("S/ 19.05");
  });
});

describe("complaints book", () => {
  test("shows the business and asks for the required data", async () => {
    const api = mockApi({ [COMPLAINTS]: () => json(FILED, 201) });
    await renderPage("/libro-de-reclamaciones");

    expect(await screen.findByText(new RegExp(`RUC ${testBusiness.ruc}`))).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de enviar" }));

    expect(await screen.findAllByText("Completa este dato.")).toHaveLength(3);
    expect(
      screen.getByText("Para responderte por correo necesitamos tu correo."),
    ).toBeDefined();
    expect(api.requestsTo(COMPLAINTS)).toEqual([]);
  });

  test("a letter answer needs an address and a DNI has 8 digits", async () => {
    mockApi({});
    await renderPage("/libro-de-reclamaciones");

    await userEvent.type(await screen.findByLabelText("Número de documento"), "123");
    await userEvent.click(screen.getByLabelText("Por carta a mi domicilio"));
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de enviar" }));

    expect(await screen.findByText("El DNI tiene 8 números.")).toBeDefined();
    expect(screen.getByText("Para enviarte una carta necesitamos tu domicilio.")).toBeDefined();
  });

  test("reviews the sheet, files it and offers to print it", async () => {
    const api = mockApi({ [COMPLAINTS]: () => json(FILED, 201) });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    await renderPage("/libro-de-reclamaciones");

    await fillRequiredFields();
    await userEvent.click(screen.getByLabelText("Soy menor de edad"));
    await userEvent.type(
      screen.getByLabelText("Nombre de tu padre, madre o representante"),
      "Rosa Mamani",
    );
    await userEvent.type(screen.getByLabelText("Monto reclamado en soles (opcional)"), "19");
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de enviar" }));

    expect(await screen.findByRole("heading", { name: "Revisa tu reclamo" })).toBeDefined();
    expect(screen.getByText("S/ 19.00")).toBeDefined();
    expect(api.requestsTo(COMPLAINTS)).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "Enviar reclamo" }));

    expect(await screen.findByRole("heading", { name: "Registramos tu reclamo" })).toBeDefined();
    expect(screen.getAllByText(/000000001-2026/).length).toBeGreaterThan(0);
    expect(screen.getByText(/13\/11\/2026/)).toBeDefined();
    expect(screen.getByText(/23\/10\/2026.*10:05/)).toBeDefined();
    expect(
      screen.getByText(
        "Te enviaremos una copia a ana@example.com en unos minutos. Igual guarda o imprime esta hoja.",
      ),
    ).toBeDefined();
    const [request] = api.requestsTo(COMPLAINTS);
    expect(await request?.json()).toEqual({
      full_name: "Ana Quispe Mamani",
      document_type: "dni",
      document_number: "12345678",
      address: null,
      email: "ana@example.com",
      phone: null,
      guardian: { full_name: "Rosa Mamani", address: null, phone: null, email: null },
      item_kind: "service",
      claimed_amount_cents: 1900,
      item_description: null,
      kind: "claim",
      detail: "Me cobraron dos veces la suscripción.",
      request: null,
      response_channel: "email",
    });

    await userEvent.click(screen.getByRole("button", { name: "Imprimir o guardar como PDF" }));
    expect(print).toHaveBeenCalledOnce();
  });

  test("lets the consumer correct the sheet before sending", async () => {
    mockApi({});
    await renderPage("/libro-de-reclamaciones");

    await fillRequiredFields();
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de enviar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Corregir" }));

    const name = screen.getByLabelText<HTMLInputElement>("Nombre completo");
    expect(name.value).toBe("Ana Quispe Mamani");
  });

  test("asks to print the sheet and email it when the book fails", async () => {
    mockApi({ [COMPLAINTS]: 500 });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    await renderPage("/libro-de-reclamaciones");

    await fillRequiredFields();
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de enviar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Enviar reclamo" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Imprime o guarda esta hoja y envíala a reclamos@example.com",
    );
    await userEvent.click(screen.getByRole("button", { name: "Imprimir o guardar como PDF" }));
    expect(print).toHaveBeenCalledOnce();
  });

  test("shows the official notice in its footer", async () => {
    mockApi({});
    await renderPage("/libro-de-reclamaciones");

    expect(await screen.findByRole("link", { name: "Libro de Reclamaciones" })).toBeDefined();
  });

  test("explains when there were too many attempts", async () => {
    mockApi({ [COMPLAINTS]: 429 });
    await renderPage("/libro-de-reclamaciones");

    await fillRequiredFields();
    await userEvent.click(screen.getByRole("button", { name: "Revisar antes de enviar" }));
    await userEvent.click(await screen.findByRole("button", { name: "Enviar reclamo" }));

    expect((await screen.findByRole("alert")).textContent).toContain("muchos intentos");
  });
});
