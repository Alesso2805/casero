import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";
import { isValidRuc, rucGroup } from "./ruc";

const SUNAT_RUC = "20131312955";
const EMPTY = {
  display_name: "Ana",
  taxpayer_kind: "person",
  ruc: null,
  ruc_group: null,
  daily_digest: false,
  declarant_locked: false,
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

describe("RUC check", () => {
  test("matches the server's check digit and groups", () => {
    expect(isValidRuc(SUNAT_RUC)).toBe(true);
    expect(isValidRuc("20131312954")).toBe(false);
    expect(isValidRuc("2013131295")).toBe(false);
    expect(rucGroup(SUNAT_RUC, false)).toBe("4-5");
    expect(rucGroup(SUNAT_RUC, true)).toBe("bc");
    expect(rucGroup("", true)).toBeNull();
  });
});

describe("profile page", () => {
  test("explains what a missing RUC means and refuses a wrong one", async () => {
    const api = mockApi({
      "/api/app/account/profile": (request) => request.method === "GET" ? json(EMPTY) : new Response(null, { status: 500 }),
    });
    await renderPage("/app/mis-datos");

    expect(await screen.findByText(/no la fecha límite de cada formulario/)).toBeDefined();
    await userEvent.type(screen.getByLabelText(/^RUC/), "20131312954");
    await userEvent.click(screen.getByRole("button", { name: "Guardar mis datos" }));

    expect(await screen.findByText(/Ese RUC no es válido/)).toBeDefined();
    expect(api.requestsTo("/api/app/account/profile").map((r) => r.method)).toEqual(["GET"]);
  });

  test("shows the schedule group and saves the profile", async () => {
    const api = mockApi({
      "/api/app/account/profile": (request) =>
        request.method === "GET"
          ? json(EMPTY)
          : json({ ...EMPTY, ruc: SUNAT_RUC, ruc_group: "bc", daily_digest: true }),
    });
    await renderPage("/app/mis-datos");

    await userEvent.type(await screen.findByLabelText(/^RUC/), SUNAT_RUC);
    expect(screen.getByText(/RUC que terminan en 4 o 5/)).toBeDefined();
    await userEvent.click(screen.getByLabelText("SUNAT me calificó como buen contribuyente"));
    expect(screen.getByText(/las de los buenos contribuyentes/)).toBeDefined();
    await userEvent.click(screen.getByLabelText("Quiero un resumen diario por correo"));
    await userEvent.click(screen.getByRole("button", { name: "Guardar mis datos" }));

    expect(await screen.findByRole("status")).toHaveProperty(
      "textContent",
      "Listo, guardamos tus datos.",
    );
    const [, request] = api.requestsTo("/api/app/account/profile");
    expect(request?.method).toBe("PUT");
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(await request?.json()).toEqual({
      display_name: "Ana",
      taxpayer_kind: "person",
      ruc: SUNAT_RUC,
      good_taxpayer: true,
      daily_digest: true,
    });
  });

  test("explains that an estate needs its own account", async () => {
    mockApi({ "/api/app/account/profile": () => json(EMPTY) });
    await renderPage("/app/mis-datos");

    await userEvent.click(await screen.findByLabelText("Una sucesión indivisa"));

    expect(screen.getByText(/necesitas otra cuenta de Casero/)).toBeDefined();
    expect(screen.getByText("Son los 11 números del RUC de la sucesión.")).toBeDefined();
  });

  test("keeps the declarant type once the account has properties", async () => {
    const api = mockApi({
      "/api/app/account/profile": (request) =>
        request.method === "GET"
          ? json({ ...EMPTY, declarant_locked: true })
          : json({ ...EMPTY, display_name: "Ana Q.", declarant_locked: true }),
    });
    await renderPage("/app/mis-datos");

    expect(await screen.findByText(/esta cuenta tiene inmuebles registrados/)).toBeDefined();
    expect(screen.queryByLabelText("Una sucesión indivisa")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Guardar mis datos" }));

    await screen.findByRole("status");
    const [, request] = api.requestsTo("/api/app/account/profile");
    expect(((await request?.json()) as { taxpayer_kind: string }).taxpayer_kind).toBe("person");
  });

  test("shows the server's RUC refusal on the field", async () => {
    mockApi({
      "/api/app/account/profile": (request) =>
        request.method === "GET" ? json(EMPTY) : json({ detail: "invalid_ruc" }, 422),
    });
    await renderPage("/app/mis-datos");

    await userEvent.type(await screen.findByLabelText(/^RUC/), SUNAT_RUC);
    await userEvent.click(screen.getByRole("button", { name: "Guardar mis datos" }));

    expect(await screen.findByText(/Ese RUC no es válido/)).toBeDefined();
  });

  test("tells a paused account why it can't edit", async () => {
    mockApi({ "/api/app/account/profile": () => json({ detail: "email_unverified" }, 403) });
    await renderPage("/app/mis-datos");

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Tu cuenta está pausada hasta que confirmes tu correo.",
    );
  });

  test("sends visitors without a session to log in", async () => {
    mockApi({ "/api/app/account/profile": 401 });
    await renderPage("/app/mis-datos");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });
});
