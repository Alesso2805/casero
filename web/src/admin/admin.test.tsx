import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderAdmin } from "./testing";

const STAFF = { email: "personal@example.com" };
const ACCOUNT = {
  id: "0193a9e0-0000-7000-8000-000000000001",
  email: "casera@example.com",
  display_name: "Ana",
  created_at: "2026-10-27T15:00:00Z",
  email_verified: true,
  deletion_requested_at: null,
  purged_at: null,
  status: "trial",
  plan_code: "casero",
  trial_ends_at: "2026-11-26",
  ends_at: "2026-11-26",
  founder: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("logging in to the panel", () => {
  async function fillIn(code: string) {
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Correo"), STAFF.email);
    await user.type(screen.getByLabelText("Contraseña"), "una-clave-larga");
    await user.type(screen.getByLabelText("Código de tu app de autenticación"), code);
    await user.click(screen.getByRole("button", { name: "Ingresar" }));
  }

  test("sends the three factors and opens the panel", async () => {
    const mock = mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/session": 204,
      "/api/admin/me": () => json(STAFF),
    });
    await renderAdmin("/admin/ingresar");

    await fillIn("123456");

    expect(await screen.findByRole("heading", { name: "Cuentas" })).toBeDefined();
    const [request] = mock.requestsTo("/api/admin/session");
    expect(await request?.clone().json()).toEqual({
      email: STAFF.email,
      password: "una-clave-larga",
      code: "123456",
    });
  });

  test("reaches the panel when it was sent to the login, which is the usual way in", async () => {
    let signedIn = false;
    mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/session": () => {
        signedIn = true;
        return new Response(null, { status: 204 });
      },
      "/api/admin/me": () => (signedIn ? json(STAFF) : new Response(null, { status: 401 })),
    });
    await renderAdmin("/admin/");

    await fillIn("123456");

    expect(await screen.findByRole("heading", { name: "Cuentas" })).toBeDefined();
  });

  test("says the same thing whichever factor was wrong", async () => {
    mockApi({ "/api/admin/csrf": 204, "/api/admin/session": 401 });
    await renderAdmin("/admin/ingresar");

    await fillIn("000000");

    expect(
      await screen.findByText("El correo, la contraseña o el código no son correctos."),
    ).toBeDefined();
  });

  test("offers the recovery code for when the app isn't at hand", async () => {
    mockApi({});
    await renderAdmin("/admin/ingresar");

    expect(
      await screen.findByText("Si no tienes la app a mano, usa un código de recuperación."),
    ).toBeDefined();
  });

  test("sends anyone without a session to the login", async () => {
    mockApi({ "/api/admin/me": 401 });
    await renderAdmin("/admin/");

    expect(await screen.findByRole("heading", { name: "Panel de Casero" })).toBeDefined();
  });

  test("logging out goes back to the login", async () => {
    mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/session": 204,
      "/api/admin/me": () => json(STAFF),
    });
    await renderAdmin("/admin/");

    await userEvent.setup().click(await screen.findByRole("button", { name: "Salir" }));

    expect(await screen.findByRole("heading", { name: "Panel de Casero" })).toBeDefined();
  });
});

describe("finding an account", () => {
  async function search(term: string) {
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Correo de la cuenta"), term);
    await user.click(screen.getByRole("button", { name: "Buscar" }));
  }

  test("shows the account with where its subscription stands", async () => {
    const mock = mockApi({
      "/api/admin/me": () => json(STAFF),
      "/api/admin/accounts": () => json([ACCOUNT]),
    });
    await renderAdmin("/admin/");

    await search("casera");

    expect(await screen.findByText(ACCOUNT.email)).toBeDefined();
    expect(screen.getByText("En prueba · 26/11/2026")).toBeDefined();
    const [request] = mock.requestsTo("/api/admin/accounts");
    expect(new URL(request?.url ?? "").searchParams.get("email")).toBe("casera");
  });

  test("forgets what was on screen when logging out", async () => {
    mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/session": 204,
      "/api/admin/me": () => json(STAFF),
      "/api/admin/accounts": () => json([ACCOUNT]),
    });
    const { queryClient } = await renderAdmin("/admin/");
    await search("casera");
    await screen.findByText(ACCOUNT.email);

    await userEvent.setup().click(screen.getByRole("button", { name: "Salir" }));

    await screen.findByRole("heading", { name: "Panel de Casero" });
    expect(queryClient.getQueryData(["accounts", "casera"])).toBeUndefined();
  });

  test("says so when nothing matches", async () => {
    mockApi({ "/api/admin/me": () => json(STAFF), "/api/admin/accounts": () => json([]) });
    await renderAdmin("/admin/");

    await search("nadie");

    expect(await screen.findByText("No hay cuentas con ese correo.")).toBeDefined();
  });

  test("asks for three letters before searching", async () => {
    const mock = mockApi({ "/api/admin/me": () => json(STAFF) });
    await renderAdmin("/admin/");

    await search("ab");

    expect(await screen.findByText("Escribe al menos 3 letras.")).toBeDefined();
    expect(mock.requestsTo("/api/admin/accounts")).toEqual([]);
  });

  test("points to logging in again when the session ended", async () => {
    mockApi({ "/api/admin/me": () => json(STAFF), "/api/admin/accounts": 401 });
    await renderAdmin("/admin/");

    await search("casera");

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain("vuelve a ingresar");
    });
  });
});
