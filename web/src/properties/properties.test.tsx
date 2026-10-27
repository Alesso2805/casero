import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";

const PROFILE = {
  display_name: "Ana",
  taxpayer_kind: "person",
  ruc: null,
  ruc_group: null,
  daily_digest: false,
  declarant_locked: false,
};
const ROOM = {
  id: "0195a0b0-0000-7000-8000-000000000002",
  property_id: "0195a0b0-0000-7000-8000-000000000001",
  name: "Cuarto 1",
  kind: "room",
  archived: false,
};
const HOUSE = {
  id: "0195a0b0-0000-7000-8000-000000000001",
  name: "Casa de Surco",
  address_line: null,
  district: "Surco",
  ownership: "sole",
  autovaluo_cents: null,
  rented_share_pct: 100,
  archived: false,
  units: [ROOM],
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

describe("properties list", () => {
  test("invites a new landlord to add a property", async () => {
    mockApi({ "/api/app/properties": () => json([]) });
    await renderPage("/app/inmuebles");

    expect(await screen.findByText(/Todavía no registras inmuebles/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Agregar inmueble" })).toBeDefined();
  });

  test("shows each property with its units and keeps archived ones apart", async () => {
    const archived = { ...HOUSE, id: "0195a0b0-0000-7000-8000-000000000009", name: "Local viejo", archived: true };
    mockApi({ "/api/app/properties": () => json([HOUSE, archived]) });
    await renderPage("/app/inmuebles");

    expect(await screen.findByRole("heading", { name: "Casa de Surco" })).toBeDefined();
    expect(screen.getByText("Cuarto 1 · Cuarto")).toBeDefined();
    expect(screen.getByText("Archivados (1)")).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Local viejo" })).toBeNull();
  });

  test("sends visitors without a session to log in", async () => {
    mockApi({ "/api/app/properties": 401 });
    await renderPage("/app/inmuebles");

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
  });
});

describe("new property", () => {
  test("saves the property with its units and goes back to the list", async () => {
    const api = mockApi({
      "/api/app/account/profile": () => json(PROFILE),
      "/api/app/properties": (request) => (request.method === "POST" ? json(HOUSE, 201) : json([HOUSE])),
    });
    await renderPage("/app/inmuebles/nuevo");

    await userEvent.type(await screen.findByLabelText("Nombre del inmueble"), "Casa de Surco");
    await userEvent.type(screen.getByLabelText("Distrito (opcional)"), "Surco");
    await userEvent.type(screen.getByLabelText("Autovalúo en soles (opcional)"), "250000.50");
    await userEvent.clear(screen.getByLabelText("¿Qué porcentaje del inmueble alquilas?"));
    await userEvent.type(screen.getByLabelText("¿Qué porcentaje del inmueble alquilas?"), "40");
    await userEvent.type(screen.getByLabelText("Nombre de la unidad 1"), "Cuarto 1");
    await userEvent.click(screen.getByRole("button", { name: "Agregar otra unidad" }));
    await userEvent.type(screen.getByLabelText("Nombre de la unidad 2"), "Cochera");
    await userEvent.selectOptions(screen.getByLabelText("Tipo de la unidad 2"), "parking");
    await userEvent.click(screen.getByRole("button", { name: "Guardar inmueble" }));

    expect(await screen.findByRole("heading", { name: "Mis inmuebles" })).toBeDefined();
    const [request] = api.requestsTo("/api/app/properties").filter((r) => r.method === "POST");
    expect(request?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(await request?.json()).toEqual({
      name: "Casa de Surco",
      address_line: null,
      district: "Surco",
      ownership: "sole",
      conjugal_option_confirmed: false,
      autovaluo_cents: 25000050,
      rented_share_pct: 40,
      units: [
        { name: "Cuarto 1", kind: "room" },
        { name: "Cochera", kind: "parking" },
      ],
    });
  });

  test("asks to confirm the conjugal option and checks the numbers", async () => {
    const api = mockApi({ "/api/app/account/profile": () => json(PROFILE) });
    await renderPage("/app/inmuebles/nuevo");

    await userEvent.type(await screen.findByLabelText("Nombre del inmueble"), "Casa");
    await userEvent.click(screen.getByLabelText("De mi sociedad conyugal, y yo declaro por los dos"));
    await userEvent.type(screen.getByLabelText("Autovalúo en soles (opcional)"), "250,000");
    await userEvent.clear(screen.getByLabelText("¿Qué porcentaje del inmueble alquilas?"));
    await userEvent.type(screen.getByLabelText("¿Qué porcentaje del inmueble alquilas?"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Guardar inmueble" }));

    expect(await screen.findByText(/confirma que el RUC de esta cuenta/)).toBeDefined();
    expect(screen.getByText(/sin comas de miles/)).toBeDefined();
    expect(screen.getByText("Escribe un número del 1 al 100.")).toBeDefined();
    expect(screen.getAllByText("Completa este dato.")).toHaveLength(1);
    expect(api.requestsTo("/api/app/properties")).toHaveLength(0);
  });

  test("an estate account registers only estate properties", async () => {
    const api = mockApi({
      "/api/app/account/profile": () => json({ ...PROFILE, taxpayer_kind: "estate" }),
      "/api/app/properties": (request) => (request.method === "POST" ? json(HOUSE, 201) : json([HOUSE])),
    });
    await renderPage("/app/inmuebles/nuevo");

    expect(await screen.findByText(/se declaran con el RUC de la sucesión/)).toBeDefined();
    expect(screen.queryByLabelText("Solo mío")).toBeNull();
    await userEvent.type(screen.getByLabelText("Nombre del inmueble"), "Casa de la familia");
    await userEvent.type(screen.getByLabelText("Nombre de la unidad 1"), "Departamento");
    await userEvent.click(screen.getByRole("button", { name: "Guardar inmueble" }));

    await screen.findByRole("heading", { name: "Mis inmuebles" });
    const [request] = api.requestsTo("/api/app/properties").filter((r) => r.method === "POST");
    expect(((await request?.json()) as { ownership: string }).ownership).toBe("estate");
  });
});

describe("edit property", () => {
  const unit = ROOM;
  const editable = { ...HOUSE, autovaluo_cents: 25000050 };

  test("is reached from the list", async () => {
    mockApi({ "/api/app/properties": () => json([HOUSE]) });
    await renderPage("/app/inmuebles");

    const link = await screen.findByRole("link", { name: "Ver y editar Casa de Surco" });
    expect(link.getAttribute("href")).toBe(`/app/inmuebles/${HOUSE.id}`);
  });

  test("saves the property's details", async () => {
    const api = mockApi({
      "/api/app/account/profile": () => json(PROFILE),
      "/api/app/properties": () => json([editable]),
      [`/api/app/properties/${HOUSE.id}`]: () => json(editable),
    });
    await renderPage(`/app/inmuebles/${HOUSE.id}`);

    const autovaluo = await screen.findByLabelText("Autovalúo en soles (opcional)");
    expect(autovaluo).toHaveProperty("value", "250000.50");
    await userEvent.clear(screen.getByLabelText("Nombre del inmueble"));
    await userEvent.type(screen.getByLabelText("Nombre del inmueble"), "Casa de Barranco");
    await userEvent.click(screen.getByRole("button", { name: "Guardar inmueble" }));

    expect(await screen.findByRole("status")).toHaveProperty(
      "textContent",
      "Listo, guardamos los cambios.",
    );
    const [request] = api.requestsTo(`/api/app/properties/${HOUSE.id}`);
    expect(request?.method).toBe("PUT");
    expect(await request?.json()).toMatchObject({
      name: "Casa de Barranco",
      autovaluo_cents: 25000050,
    });
  });

  test("edits and adds units", async () => {
    const api = mockApi({
      "/api/app/account/profile": () => json(PROFILE),
      "/api/app/properties": () => json([HOUSE]),
      [`/api/app/units/${unit.id}`]: () => json({ ...unit, name: "Cuarto grande" }),
      [`/api/app/properties/${HOUSE.id}/units`]: () => json(unit, 201),
    });
    await renderPage(`/app/inmuebles/${HOUSE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Editar Cuarto 1" }));
    const name = within(screen.getByRole("list")).getByLabelText("Nombre de la unidad");
    await userEvent.clear(name);
    await userEvent.type(name, "Cuarto grande");
    await userEvent.click(screen.getByRole("button", { name: "Guardar unidad" }));
    await screen.findByRole("button", { name: "Editar Cuarto 1" });

    const add = screen.getByRole("form", { name: "Agregar una unidad" });
    await userEvent.type(within(add).getByLabelText("Nombre de la unidad"), "Cochera");
    await userEvent.selectOptions(within(add).getByLabelText("Tipo de unidad"), "parking");
    await userEvent.click(within(add).getByRole("button", { name: "Agregar unidad" }));

    await vi.waitFor(() => {
      expect(api.requestsTo(`/api/app/properties/${HOUSE.id}/units`)).toHaveLength(1);
    });
    const [edited] = api.requestsTo(`/api/app/units/${unit.id}`);
    expect(await edited?.json()).toEqual({ name: "Cuarto grande", kind: "room" });
    const [added] = api.requestsTo(`/api/app/properties/${HOUSE.id}/units`);
    expect(await added?.json()).toEqual({ name: "Cochera", kind: "parking" });
  });

  test("explains why a rented unit can't be archived", async () => {
    mockApi({
      "/api/app/account/profile": () => json(PROFILE),
      "/api/app/properties": () => json([HOUSE]),
      [`/api/app/units/${unit.id}/archive`]: () => json({ detail: "active_lease" }, 409),
    });
    await renderPage(`/app/inmuebles/${HOUSE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Archivar Cuarto 1" }));
    expect(screen.getByText(/Ya no podrás registrar contratos en esta unidad/)).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "Sí, archivar" }));

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Esta unidad tiene un contrato activo. Termínalo antes de archivarla.",
    );
  });

  test("archives the property after confirming", async () => {
    const api = mockApi({
      "/api/app/account/profile": () => json(PROFILE),
      "/api/app/properties": () => json([HOUSE]),
      [`/api/app/properties/${HOUSE.id}/archive`]: () => json({ ...HOUSE, archived: true }),
    });
    await renderPage(`/app/inmuebles/${HOUSE.id}`);

    await userEvent.click(await screen.findByRole("button", { name: "Archivar inmueble" }));
    await userEvent.click(screen.getByRole("button", { name: "Sí, archivar" }));

    expect(await screen.findByRole("heading", { name: "Mis inmuebles" })).toBeDefined();
    expect(api.requestsTo(`/api/app/properties/${HOUSE.id}/archive`)).toHaveLength(1);
  });

  test("says when the property doesn't exist", async () => {
    mockApi({
      "/api/app/account/profile": () => json(PROFILE),
      "/api/app/properties": () => json([]),
    });
    await renderPage(`/app/inmuebles/${HOUSE.id}`);

    expect(await screen.findByText("No encontramos este inmueble.")).toBeDefined();
  });
});
