import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { json, mockApi, testAccount, testBusiness } from "../test/api";
import { renderPage } from "../test/render";

const ME = {
  user_id: "01a175b4-8f38-727d-a7dc-40a7a7b30001",
  email: "ana@example.com",
  email_verified: false,
  verify_by: "2026-11-02T15:00:00Z",
  blocked_until_verified: false,
};

const EMPTY_HOME = {
  "/api/app/tax/upcoming": () => json(null),
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

describe("my plan", () => {
  const PLANS = [
    {
      code: "free",
      name: "Gratis",
      price_month_cents: 0,
      price_year_cents: 0,
      max_active_leases: 1,
    },
    {
      code: "casero",
      name: "Casero",
      price_month_cents: 1900,
      price_year_cents: 19000,
      max_active_leases: 10,
    },
  ];

  test("shows the plan, its prices from the server and how to pay by Yape", async () => {
    mockApi({ "/api/app/account": () => json(testAccount), "/api/app/plans": () => json(PLANS) });
    await renderPage("/app/plan");

    expect(
      await screen.findByText("Estás en la prueba gratis de Casero hasta el 26/11/2026."),
    ).toBeDefined();
    expect(await screen.findByText("S/ 19.00 al mes o S/ 190.00 al año")).toBeDefined();
    expect(screen.getByText("Hasta 1 contrato activo")).toBeDefined();
    expect(
      await screen.findByText(
        `Yapea el monto del plan al ${testBusiness.yape}, a nombre de ${testBusiness.name}.`,
      ),
    ).toBeDefined();
  });

  test.each([
    [{ status: "active", ends_at: "2027-01-31" }, "Tienes el plan Casero hasta el 31/01/2027."],
    [{ status: "active", ends_at: null }, "Tienes el plan Casero."],
    [
      { status: "grace", grace_until: "2026-12-02" },
      "Tu plan venció, pero puedes seguir usando todo hasta el 02/12/2026.",
    ],
    [{ status: "free" }, "Estás en el plan Gratis."],
  ])("says where the account stands", async (account, message) => {
    mockApi({
      "/api/app/account": () => json({ ...testAccount, ...account }),
      "/api/app/plans": () => json(PLANS),
    });
    await renderPage("/app/plan");

    expect(await screen.findByText(message)).toBeDefined();
  });

  test("leaves out how to pay when no Yape number is configured", async () => {
    mockApi({
      "/api/public/business": () => json({ ...testBusiness, yape: "" }),
      "/api/app/plans": () => json(PLANS),
    });
    const { settled } = await renderPage("/app/plan");

    expect(await screen.findByRole("heading", { name: "Los planes" })).toBeDefined();
    await settled();
    expect(screen.queryByRole("heading", { name: "Cómo pagar" })).toBeNull();
  });

  test("sends a visitor without a session to log in", async () => {
    mockApi({ "/api/app/account": 401, "/api/app/plans": 401 });
    await renderPage("/app/plan");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });

  test("on the home page, tells that the trial ended and what's owed to SUNAT", async () => {
    mockApi({
      "/api/app/me": () => json({ ...ME, email_verified: true, verify_by: null }),
      ...EMPTY_HOME,
      "/api/app/account": () =>
        json({ ...testAccount, status: "grace", grace_until: "2026-12-02" }),
      "/api/app/tax/pending-dues": () =>
        json([{ period: "2026-10", due_on: "2026-11-19", pending_cents: 4000 }]),
    });
    await renderPage("/app");

    expect(await screen.findByText(/Tu prueba gratis terminó/)).toBeDefined();
    expect(await screen.findByText("octubre de 2026: S/ 40.00, vencen el 19/11/2026")).toBeDefined();
    expect(screen.getByRole("link", { name: "Ver mi plan" })).toHaveProperty(
      "pathname",
      "/app/plan",
    );
  });

  test("says nothing about the trial to a paying account in grace", async () => {
    mockApi({
      "/api/app/me": () => json({ ...ME, email_verified: true, verify_by: null }),
      ...EMPTY_HOME,
      "/api/app/account": () =>
        json({
          ...testAccount,
          status: "grace",
          ends_at: "2027-01-31",
          grace_until: "2027-02-06",
        }),
    });
    const { settled } = await renderPage("/app");

    expect(await screen.findByRole("link", { name: "Mi plan" })).toBeDefined();
    await settled();
    expect(screen.queryByText(/Tu prueba gratis terminó/)).toBeNull();
  });
});

describe("cancelling a deletion", () => {
  const PATH = "/api/public/account-deletion/cancellation";

  test("asks first, because mail filters open links", async () => {
    const api = mockApi({ [PATH]: 204 });
    await renderPage("/cancelar-eliminacion#token=el-token");

    const confirm = await screen.findByRole("button", { name: "Sí, conservar mi cuenta" });
    expect(api.requestsTo(PATH)).toHaveLength(0);
    await userEvent.click(confirm);

    expect((await screen.findByRole("status")).textContent).toContain("tu cuenta sigue activa");
    expect(await api.requestsTo(PATH)[0]?.json()).toEqual({ token: "el-token" });
  });

  test.each([
    [400, "Este enlace no funciona"],
    [409, "Ese correo ya tiene otra cuenta"],
  ])("explains a %i", async (status, message) => {
    mockApi({ [PATH]: status });
    await renderPage("/cancelar-eliminacion#token=el-token");

    await userEvent.click(await screen.findByRole("button", { name: "Sí, conservar mi cuenta" }));

    expect((await screen.findByRole("alert")).textContent).toContain(message);
  });

  test("says when the link has no token", async () => {
    mockApi({});
    await renderPage("/cancelar-eliminacion");

    expect((await screen.findByRole("alert")).textContent).toContain("Este enlace no funciona");
    expect(screen.queryByRole("button", { name: "Sí, conservar mi cuenta" })).toBeNull();
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

  test.each([
    [3, "Tus formularios 1683 de octubre de 2026 vencen el 19/11/2026 (en 3 días): falta pagar S/ 43.00."],
    [1, "Mañana vencen tus formularios 1683 de octubre de 2026: falta pagar S/ 43.00."],
    [0, "Hoy vencen tus formularios 1683 de octubre de 2026: falta pagar S/ 43.00."],
  ])("warns %i days before the 1683 falls due", async (days, notice) => {
    mockApi({
      "/api/app/me": () => json({ ...ME, email_verified: true, verify_by: null }),
      ...EMPTY_HOME,
      "/api/app/tax/upcoming": () =>
        json({
          period: "2026-10",
          due_on: "2026-11-19",
          days_left: days,
          pending_cents: 4300,
          declarations: 2,
        }),
    });
    await renderPage("/app");

    expect(await screen.findByText(notice)).toBeDefined();
    expect(screen.getByRole("link", { name: "Ver formularios" })).toHaveProperty(
      "pathname",
      "/app/impuestos",
    );
  });

  test("says when SUNAT's due dates could not be checked", async () => {
    mockApi({
      "/api/app/me": () => json({ ...ME, email_verified: true, verify_by: null }),
      ...EMPTY_HOME,
      "/api/app/tax/upcoming": 500,
    });
    await renderPage("/app");

    expect(
      await screen.findByText(
        "No pudimos revisar tus vencimientos de SUNAT. Vuelve a intentarlo en unos minutos.",
      ),
    ).toBeDefined();
  });

  const VERIFIED = () => json({ ...ME, email_verified: true, verify_by: null });
  const NEW_TERMS = {
    id: "01a175b4-8f38-727d-a7dc-40a7a7b30002",
    kind: "terms",
    version: "0.2",
    url: "/legal/terminos/0.2",
  };
  const CONSENT = {
    id: "01a175b4-8f38-727d-a7dc-40a7a7b30003",
    kind: "sensitive_consent",
    version: "0.1",
    url: "/legal/consentimiento-datos-sensibles/0.1",
  };

  test("asks to accept a new version before showing the account", async () => {
    let accepted = false;
    const api = mockApi({
      "/api/app/me": VERIFIED,
      ...EMPTY_HOME,
      "/api/app/legal": () =>
        json({ pending: accepted ? [] : [NEW_TERMS], consent_withdrawn: false }),
      "/api/app/legal/acceptances": () => {
        accepted = true;
        return json({ pending: [], consent_withdrawn: false });
      },
    });
    await renderPage("/app");

    expect(
      await screen.findByRole("heading", { name: "Actualizamos nuestros documentos" }),
    ).toBeDefined();
    expect(screen.queryByRole("link", { name: "Mis inmuebles" })).toBeNull();
    expect(screen.getByRole("link", { name: "Descargar mis datos" })).toBeDefined();
    expect(screen.getByRole("link", { name: "términos y condiciones" })).toHaveProperty(
      "pathname",
      "/legal/terminos/0.2",
    );
    const submit = screen.getByRole("button", { name: "Aceptar y continuar" });
    expect(submit).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByLabelText(/Acepto los/));
    await userEvent.click(submit);

    expect(await screen.findByRole("link", { name: "Mis inmuebles" })).toBeDefined();
    expect(await api.requestsTo("/api/app/legal/acceptances")[0]?.json()).toEqual({
      document_ids: [NEW_TERMS.id],
    });
  });

  test("a withdrawn consent blocks the account until it is given again", async () => {
    mockApi({
      "/api/app/me": VERIFIED,
      ...EMPTY_HOME,
      "/api/app/legal": () => json({ pending: [CONSENT], consent_withdrawn: true }),
    });
    await renderPage("/app");

    expect(await screen.findByRole("heading", { name: "Tu cuenta está bloqueada" })).toBeDefined();
    expect(screen.queryByRole("navigation", { name: "Principal" })).toBeNull();
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Eliminar mi cuenta" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Descargar mis datos" })).toHaveProperty(
      "pathname",
      "/api/app/exports/my-data.zip",
    );
    expect(
      await screen.findByLabelText(new RegExp(`Consiento de forma expresa que ${testBusiness.name}`)),
    ).toBeDefined();
  });

  test("says when a newer version appeared while accepting", async () => {
    mockApi({
      "/api/app/me": VERIFIED,
      ...EMPTY_HOME,
      "/api/app/legal": () => json({ pending: [NEW_TERMS], consent_withdrawn: false }),
      "/api/app/legal/acceptances": () => json({ detail: "document_not_current" }, 422),
    });
    await renderPage("/app");

    await userEvent.click(await screen.findByLabelText(/Acepto los/));
    await userEvent.click(screen.getByRole("button", { name: "Aceptar y continuar" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Hay una versión más nueva");
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
    await renderPage("/app/mas");

    await userEvent.click(
      await screen.findByRole("button", { name: "Cerrar sesión en todos mis dispositivos" }),
    );

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
    expect(api.requestsTo("/api/app/sessions")[0]?.method).toBe("DELETE");
  });
});
