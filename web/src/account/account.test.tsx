import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { json, mockApi, testBusiness } from "../test/api";
import { renderPage } from "../test/render";

const ME = {
  user_id: "01a175b4-8f38-727d-a7dc-40a7a7b30001",
  email: "ana@example.com",
  email_verified: false,
  verify_by: "2026-11-02T15:00:00Z",
  blocked_until_verified: false,
};

const EMPTY_HOME = {
  "/api/app/collections": () => json({ due_by_month_end_cents: 0, overdue_cents: 0, leases: [] }),
  "/api/app/leases": () => json([]),
  "/api/app/renters": () => json([]),
  "/api/app/properties": () => json([]),
};

function setCsrfCookie(value: string | null) {
  // __Host- cookies must be Secure with Path=/, or the browser (and jsdom) drops them.
  document.cookie = value
    ? `__Host-casero_csrf=${value}; Path=/; Secure`
    : "__Host-casero_csrf=; Path=/; Secure; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

beforeEach(() => {
  setCsrfCookie("csrf-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  setCsrfCookie(null);
});

async function fillRegistration() {
  await userEvent.type(await screen.findByLabelText("¿Cómo te llamamos?"), "Ana");
  await userEvent.type(screen.getByLabelText("Tu correo electrónico"), "ana@example.com");
  await userEvent.type(screen.getByLabelText("Contraseña"), "una clave bien larga");
  await userEvent.click(screen.getByLabelText(/Acepto los/));
  await userEvent.click(screen.getByLabelText(/Consiento de forma expresa/));
}

describe("registration", () => {
  test("asks for every field and both acceptances", async () => {
    const api = mockApi({});
    await renderPage("/registro");

    await userEvent.type(await screen.findByLabelText("Contraseña"), "corta");
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));

    expect(await screen.findByText("La contraseña debe tener al menos 10 caracteres.")).toBeDefined();
    expect(
      screen.getByText("Para crear tu cuenta necesitas aceptar los términos y la política de privacidad."),
    ).toBeDefined();
    expect(screen.getByText(/Casero necesita tu consentimiento/)).toBeDefined();
    expect(api.requestsTo("/api/public/registration")).toEqual([]);
  });

  test("names the controller in the consent and sends the invitation", async () => {
    const api = mockApi({
      "/api/public/registration": 201,
      "/api/app/me": () => json(ME),
      ...EMPTY_HOME,
    });
    await renderPage("/registro#invitacion=abc123");

    expect(await screen.findByText(new RegExp(`que ${testBusiness.name}, responsable`))).toBeDefined();
    await fillRegistration();
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));

    expect(await screen.findByRole("heading", { name: "Inicio" })).toBeDefined();
    const [request] = api.requestsTo("/api/public/registration");
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(await request?.json()).toEqual({
      email: "ana@example.com",
      password: "una clave bien larga",
      display_name: "Ana",
      invite_token: "abc123",
      accept_terms_and_privacy: true,
      consent_sensitive_data: true,
    });
  });

  test.each([
    [403, "Necesitas una invitación válida"],
    [409, "Ya existe una cuenta con ese correo"],
    [429, "muchos intentos"],
  ])("explains a %i", async (status, message) => {
    mockApi({ "/api/public/registration": status });
    await renderPage("/registro");

    await fillRegistration();
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));

    expect((await screen.findByRole("alert")).textContent).toContain(message);
  });

  test("fetches a CSRF cookie before the first unsafe request", async () => {
    setCsrfCookie(null);
    const api = mockApi({
      "/api/public/csrf": () => {
        setCsrfCookie("fresh");
        return new Response(null, { status: 204 });
      },
      "/api/public/registration": 409,
    });
    await renderPage("/registro");

    await fillRegistration();
    await userEvent.click(screen.getByRole("button", { name: "Crear mi cuenta" }));

    await screen.findByRole("alert");
    const [request] = api.requestsTo("/api/public/registration");
    expect(api.requestsTo("/api/public/csrf")).toHaveLength(1);
    expect(request?.headers.get("X-CSRF-Token")).toBe("fresh");
  });
});

describe("login", () => {
  test("refuses wrong credentials and opens the account with the right ones", async () => {
    let attempts = 0;
    mockApi({
      "/api/public/session": () => new Response(null, { status: ++attempts === 1 ? 401 : 204 }),
      "/api/app/me": () => json(ME),
      ...EMPTY_HOME,
    });
    await renderPage("/ingresar");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.type(screen.getByLabelText("Contraseña"), "una clave bien larga");
    await userEvent.click(screen.getByRole("button", { name: "Ingresar" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Correo o contraseña incorrectos.");

    await userEvent.click(screen.getByRole("button", { name: "Ingresar" }));
    expect(await screen.findByRole("heading", { name: "Inicio" })).toBeDefined();
  });

  test("shows and hides the password", async () => {
    mockApi({});
    await renderPage("/ingresar");

    const password = await screen.findByLabelText<HTMLInputElement>("Contraseña");
    await userEvent.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(password.type).toBe("text");
  });
});

describe("account home", () => {
  test("asks to confirm the email and resends the link", async () => {
    const api = mockApi({
      "/api/app/me": () => json(ME),
      "/api/app/email-verification": 202,
      ...EMPTY_HOME,
    });
    await renderPage("/app");

    expect(
      await screen.findByText(
        "Confirma tu correo: te enviamos un enlace a ana@example.com. Tienes hasta el 02/11/2026 para confirmarlo.",
      ),
    ).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Reenviar el correo" }));

    expect((await screen.findByRole("status")).textContent).toContain("nuevo enlace");
    expect(api.requestsTo("/api/app/email-verification")[0]?.headers.get("X-CSRF-Token")).toBe(
      "csrf-token",
    );
  });

  test("says when the account could not be loaded", async () => {
    mockApi({ "/api/app/me": 500 });
    await renderPage("/app");

    expect(await screen.findByText(/No pudimos cargar tu cuenta/)).toBeDefined();
  });

  test("sends a signed-out visitor to the login and logs out", async () => {
    mockApi({ "/api/app/me": 401 });
    await renderPage("/app");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });

  test("logs out everywhere", async () => {
    const api = mockApi({
      "/api/app/me": () => json({ ...ME, email_verified: true, verify_by: null }),
      "/api/app/sessions": 204,
      ...EMPTY_HOME,
    });
    await renderPage("/app");

    await userEvent.click(
      await screen.findByRole("button", { name: "Cerrar sesión en todos mis dispositivos" }),
    );

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
    expect(api.requestsTo("/api/app/sessions")[0]?.method).toBe("DELETE");
  });
});
