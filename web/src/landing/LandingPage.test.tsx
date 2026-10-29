import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { mockApi, testBusiness } from "../test/api";
import { renderPage } from "../test/render";

const WAITLIST = "/api/public/waitlist";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("landing page", () => {
  test("shows the promise, both plans and the complaints book", async () => {
    mockApi({});
    await renderPage("/");

    expect(await screen.findByRole("heading", { level: 1 })).toBeDefined();
    expect(document.title).toBe("Casero");
    expect(screen.getByText("S/ 0")).toBeDefined();
    expect(screen.getByText("S/ 19 al mes o S/ 190 al año")).toBeDefined();
    const links = screen.getAllByRole("link", { name: "Libro de Reclamaciones" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/libro-de-reclamaciones",
      "/libro-de-reclamaciones",
    ]);
  });

  test("asks for a valid email and for consent before sending", async () => {
    const api = mockApi({ [WAITLIST]: 202 });
    await renderPage("/");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "no-es-un-correo");
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    expect(await screen.findByText("Ese correo parece incompleto. Revisa que tenga @ y un punto, por ejemplo: nombre@gmail.com.")).toBeDefined();
    expect(screen.getByText("Marca la casilla para que podamos escribirte.")).toBeDefined();
    expect(api.requestsTo(WAITLIST)).toEqual([]);
  });

  test("joins the waitlist with consent given to the named controller", async () => {
    const api = mockApi({ [WAITLIST]: 202 });
    await renderPage("/");

    expect(await screen.findByText(new RegExp(`Acepto que ${testBusiness.name}`))).toBeDefined();

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    expect(await screen.findByRole("status")).toBeDefined();
    const [request] = api.requestsTo(WAITLIST);
    expect(await request?.json()).toEqual({
      email: "ana@example.com",
      consent: true,
      source: "landing",
    });
  });

  test("explains when there were too many attempts", async () => {
    mockApi({ [WAITLIST]: 429 });
    await renderPage("/");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    expect((await screen.findByRole("alert")).textContent).toContain("muchos intentos");
  });
});

describe("privacy page", () => {
  test("renders the privacy policy with the business identity", async () => {
    mockApi({});
    await renderPage("/privacidad");

    expect(
      await screen.findByRole("heading", { name: "Política de privacidad de Casero", level: 1 }),
    ).toBeDefined();
    expect(await screen.findByText(new RegExp(`RUC ${testBusiness.ruc}`))).toBeDefined();
    expect(screen.getByRole("link", { name: "Libro de Reclamaciones" })).toBeDefined();
  });
});
