import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { mockApi, testBusiness } from "../test/api";
import { renderPage } from "../test/render";

beforeEach(() => {
  document.cookie = "__Host-casero_csrf=csrf-token; Path=/; Secure";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.cookie = "__Host-casero_csrf=; Path=/; Secure; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("email verification", () => {
  test("confirms the email with the token of the link", async () => {
    const api = mockApi({ "/api/public/email-verification": 204 });
    await renderPage("/verificar#token=abc");

    expect((await screen.findByRole("status")).textContent).toBe("Tu correo está confirmado.");
    const requests = api.requestsTo("/api/public/email-verification");
    expect(requests).toHaveLength(1);
    expect(await requests[0]?.json()).toEqual({ token: "abc" });
  });

  test.each([
    ["/verificar#token=used", 400],
    ["/verificar", 204],
  ])("explains a used or missing link (%s)", async (path, status) => {
    mockApi({ "/api/public/email-verification": status });
    await renderPage(path);

    expect((await screen.findByRole("alert")).textContent).toContain("venció o ya se usó");
  });
});

describe("password recovery", () => {
  test("sends the link without revealing whether the account exists", async () => {
    const api = mockApi({ "/api/public/password-reset": 202 });
    await renderPage("/recuperar");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Enviarme el enlace" }));

    expect((await screen.findByRole("status")).textContent).toContain("Si existe una cuenta");
    expect(await api.requestsTo("/api/public/password-reset")[0]?.json()).toEqual({
      email: "ana@example.com",
    });
  });

  test("sets the new password with the token of the link", async () => {
    const api = mockApi({ "/api/public/password-reset/confirm": 204 });
    await renderPage("/nueva-clave#token=reset-token");

    await userEvent.type(await screen.findByLabelText("Contraseña"), "otra clave bien larga");
    await userEvent.click(screen.getByRole("button", { name: "Guardar mi nueva contraseña" }));

    expect((await screen.findByRole("status")).textContent).toContain("Tu contraseña cambió");
    expect(await api.requestsTo("/api/public/password-reset/confirm")[0]?.json()).toEqual({
      token: "reset-token",
      password: "otra clave bien larga",
    });
  });

  test("asks for a new link when the token expired", async () => {
    mockApi({ "/api/public/password-reset/confirm": 400 });
    await renderPage("/nueva-clave#token=old");

    await userEvent.type(await screen.findByLabelText("Contraseña"), "otra clave bien larga");
    await userEvent.click(screen.getByRole("button", { name: "Guardar mi nueva contraseña" }));

    expect((await screen.findByRole("alert")).textContent).toContain("venció o ya se usó");
    expect(screen.getByRole("link", { name: "Pedir un nuevo enlace" })).toBeDefined();
  });
});

describe("legal documents", () => {
  test.each([
    ["/legal/terminos", "Términos y condiciones de Casero"],
    ["/legal/privacidad/0.1", "Política de privacidad de Casero"],
    ["/legal/consentimiento-datos-sensibles", "Consentimiento para tratar tus ingresos por alquiler"],
  ])("renders %s with the business identity", async (path, title) => {
    mockApi({});
    await renderPage(path);

    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeDefined();
    expect((await screen.findAllByText(new RegExp(testBusiness.name))).length).toBeGreaterThan(0);
  });

  test("reports an unknown document", async () => {
    mockApi({});
    await renderPage("/legal/otro");

    expect((await screen.findByRole("alert")).textContent).toBe("No encontramos ese documento.");
  });
});
