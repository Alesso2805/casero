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

describe("an account", () => {
  const DETAIL = { ...ACCOUNT, payments: [] };
  const PATH = `/api/admin/accounts/${ACCOUNT.id}`;
  const PAYMENTS = `${PATH}/payments`;

  async function pay(fill: { amount?: string; boleta?: string; months?: string }) {
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Monto en soles"), fill.amount ?? "19");
    await user.type(screen.getByLabelText("Número de boleta"), fill.boleta ?? "EB01-1");
    if (fill.months) {
      await user.clear(screen.getByLabelText("Meses pagados"));
      await user.type(screen.getByLabelText("Meses pagados"), fill.months);
    }
    await user.click(screen.getByRole("button", { name: "Registrar pago" }));
  }

  test("shows its subscription and the payments recorded", async () => {
    mockApi({
      "/api/admin/me": () => json(STAFF),
      [PATH]: () =>
        json({
          ...DETAIL,
          payments: [
            {
              id: "0193a9e0-0000-7000-8000-000000000002",
              amount_cents: 19000,
              paid_on: "2026-10-20",
              method: "yape",
              boleta_number: "EB01-9",
              months: 12,
            },
          ],
        }),
    });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);

    expect(await screen.findByRole("heading", { name: ACCOUNT.email })).toBeDefined();
    expect(screen.getByText("S/ 190.00 el 20/10/2026, 12 meses, boleta EB01-9")).toBeDefined();
  });

  test("sends the payment in cents with an id, and shows it afterwards", async () => {
    let recorded = false;
    const mock = mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/me": () => json(STAFF),
      [PAYMENTS]: () => {
        recorded = true;
        return new Response(null, { status: 204 });
      },
      [PATH]: () =>
        json({
          ...DETAIL,
          ends_at: "2026-12-26",
          payments: recorded
            ? [
                {
                  id: "0193a9e0-0000-7000-8000-000000000002",
                  amount_cents: 1950,
                  paid_on: "2026-11-01",
                  method: "yape",
                  boleta_number: "EB01-1",
                  months: 1,
                },
              ]
            : [],
        }),
    });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);

    await pay({ amount: "19.50" });

    expect(await screen.findByText("Pago registrado.")).toBeDefined();
    expect(await screen.findByText(/S\/ 19\.50 el 01\/11\/2026, 1 mes, boleta EB01-1/)).toBeDefined();
    const [request] = mock.requestsTo(PAYMENTS);
    expect(await request?.clone().json()).toMatchObject({
      amount_cents: 1950,
      method: "yape",
      boleta_number: "EB01-1",
      months: 1,
    });
  });

  test("a second payment gets its own id and a retry keeps the same one", async () => {
    let answers = [500, 204, 204];
    const mock = mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/me": () => json(STAFF),
      [PAYMENTS]: () => {
        const [status = 204, ...rest] = answers;
        answers = rest;
        return new Response(null, { status });
      },
      [PATH]: () => json(DETAIL),
    });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);
    const user = userEvent.setup();

    await pay({});
    await screen.findByText("No se pudo cargar. Si tu sesión terminó, vuelve a ingresar.");
    await user.click(screen.getByRole("button", { name: "Registrar pago" }));
    await screen.findByText("Pago registrado.");
    await pay({ boleta: "EB01-2" });
    await waitFor(() => {
      expect(mock.requestsTo(PAYMENTS)).toHaveLength(3);
    });

    const ids = await Promise.all(
      mock.requestsTo(PAYMENTS).map(async (request) => {
        const body = (await request.clone().json()) as { id: string };
        return body.id;
      }),
    );
    expect(ids[1]).toBe(ids[0]);
    expect(ids[2]).not.toBe(ids[0]);
  });

  test.each([
    [{ amount: "0" }, "Escribe un monto válido, como 19 o 19.50."],
    [{ months: "25" }, "Escribe un número de meses entre 1 y 24."],
  ])("refuses impossible values before sending", async (fill, message) => {
    const mock = mockApi({ "/api/admin/me": () => json(STAFF), [PATH]: () => json(DETAIL) });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);

    await pay(fill);

    expect(await screen.findByText(message)).toBeDefined();
    expect(mock.requestsTo(PAYMENTS)).toEqual([]);
  });

  test.each([
    [422, "future_date", "La fecha del pago no puede ser futura."],
    [409, "account_closing", "Esta cuenta pidió su eliminación, así que ya no recibe pagos."],
    [409, "Conflict", "Este pago ya se registró con otros datos. Recarga la página y revísalo."],
  ])("explains a refusal from the server", async (status, detail, message) => {
    mockApi({
      "/api/admin/csrf": 204,
      "/api/admin/me": () => json(STAFF),
      [PAYMENTS]: () => json({ detail }, status),
      [PATH]: () => json(DETAIL),
    });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);

    await pay({});

    expect(await screen.findByText(message)).toBeDefined();
  });

  test("an account being deleted has no payment form", async () => {
    mockApi({
      "/api/admin/me": () => json(STAFF),
      [PATH]: () => json({ ...DETAIL, deletion_requested_at: "2026-11-01T15:00:00Z" }),
    });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);

    expect(
      await screen.findByText("Esta cuenta pidió su eliminación, así que ya no recibe pagos."),
    ).toBeDefined();
    expect(screen.queryByRole("button", { name: "Registrar pago" })).toBeNull();
  });

  test("says when the account does not exist", async () => {
    mockApi({ "/api/admin/me": () => json(STAFF), [PATH]: 404 });
    await renderAdmin(`/admin/cuentas/${ACCOUNT.id}`);

    expect(await screen.findByText("No existe esta cuenta.")).toBeDefined();
  });
});

describe("the SUNAT schedule", () => {
  test("shows a month by group of RUC, with its source", async () => {
    mockApi({
      "/api/admin/me": () => json(STAFF),
      "/api/admin/sunat-schedule": () =>
        json([
          { period: "2026-10", ruc_group: "0", due_on: "2026-11-17", source_url: "https://x.test/a" },
          { period: "2026-10", ruc_group: "bc", due_on: "2026-11-24", source_url: "https://x.test/a" },
        ]),
    });
    await renderAdmin("/admin/cronograma");

    const month = await screen.findByRole("row", { name: /octubre de 2026/ });
    expect(month.textContent).toContain("17/11/2026");
    expect(month.textContent).toContain("24/11/2026");
    expect(screen.getByRole("link", { name: "Ver la fuente en SUNAT" })).toHaveProperty(
      "href",
      "https://x.test/a",
    );
  });

  test("warns when no schedule is loaded", async () => {
    mockApi({ "/api/admin/me": () => json(STAFF), "/api/admin/sunat-schedule": () => json([]) });
    await renderAdmin("/admin/cronograma");

    expect(await screen.findByText("No hay ningún cronograma cargado.")).toBeDefined();
  });
});

describe("the complaints", () => {
  const COMPLAINT = {
    number: "000000001-2026",
    kind: "claim",
    filed_at: "2026-11-01T15:00:00Z",
    due_on: "2026-11-24",
    responded_at: null,
    response_channel: "email",
  };

  test.each([
    ["open", "Abierto"],
    ["overdue", "Vencido"],
    ["answered", "Respondido"],
  ])("shows the deadline and whether it is %s", async (state, label) => {
    mockApi({
      "/api/admin/me": () => json(STAFF),
      "/api/admin/complaints": () => json([{ ...COMPLAINT, state }]),
    });
    await renderAdmin("/admin/reclamos");

    expect(await screen.findByText(label)).toBeDefined();
    expect(screen.getByText("000000001-2026 · Reclamo")).toBeDefined();
    expect(screen.getByText("Vence el 24/11/2026")).toBeDefined();
    expect(screen.getByText("Se responde por correo")).toBeDefined();
  });

  test("says so when there are none", async () => {
    mockApi({ "/api/admin/me": () => json(STAFF), "/api/admin/complaints": () => json([]) });
    await renderAdmin("/admin/reclamos");

    expect(await screen.findByText("No hay reclamos.")).toBeDefined();
  });
});
