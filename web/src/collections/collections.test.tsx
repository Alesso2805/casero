import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";

const ME = {
  user_id: "01a175b4-8f38-727d-a7dc-40a7a7b30001",
  email: "ana@example.com",
  email_verified: true,
  verify_by: null,
  blocked_until_verified: false,
};
const PROPERTY = {
  id: "0195a0b0-0000-7000-8000-000000000001",
  name: "Casa de Surco",
  address_line: null,
  district: "Surco",
  ownership: "sole",
  autovaluo_cents: null,
  rented_share_pct: 100,
  archived: false,
  units: ["Cuarto 1", "Cuarto 2", "Cochera"].map((name, n) => ({
    id: `0195a0b0-0000-7000-8000-00000000000${String(n + 2)}`,
    property_id: "0195a0b0-0000-7000-8000-000000000001",
    name,
    kind: "room",
    archived: false,
  })),
};
const RENTERS = ["Ana Quispe", "Luis Rojas", "Rosa Huamán"].map((full_name, n) => ({
  id: `0195a0b0-0000-7000-8000-00000000001${String(n)}`,
  full_name,
  phone_e164: null,
  doc_type: null,
  doc_last4: null,
}));
const LEASES = [0, 1, 2].map((n) => ({
  id: `0195a0b0-0000-7000-8000-00000000002${String(n)}`,
  unit_id: PROPERTY.units[n]?.id,
  renter_id: RENTERS[n]?.id,
  monthly_rent_cents: 80000,
  due_day: 5,
  start_date: "2026-01-01",
  end_date: null,
  ended_at: n === 2 ? "2026-09-30" : null,
  control_from_period: "2026-09",
  tax_treatment: "standard",
  days_to_end: null,
  ending_soon: false,
}));
const line = {
  ended: false,
  overdue_days: 0,
  overdue_cents: 0,
  next_due_on: null,
  next_due_cents: 0,
  balance_cents: 0,
};
const COLLECTIONS = {
  due_by_month_end_cents: 270000,
  overdue_cents: 110000,
  leases: [
    {
      ...line,
      lease_id: LEASES[2]?.id,
      ended: true,
      status: "overdue",
      overdue_days: 1,
      overdue_cents: 30000,
      balance_cents: 30000,
    },
    {
      ...line,
      lease_id: LEASES[0]?.id,
      status: "overdue",
      overdue_days: 52,
      overdue_cents: 80000,
      next_due_on: "2026-10-29",
      next_due_cents: 80000,
      balance_cents: 160000,
    },
    {
      ...line,
      lease_id: LEASES[1]?.id,
      status: "due_soon",
      next_due_on: "2026-10-29",
      next_due_cents: 80000,
      balance_cents: 80000,
    },
  ],
};

function mockHome(collections: unknown = COLLECTIONS, reminders: unknown[] = []) {
  return mockApi({
    "/api/app/me": () => json(ME),
    "/api/app/collections": () => json(collections),
    "/api/app/whatsapp-reminders": () => json(reminders),
    "/api/app/leases": () => json(LEASES),
    "/api/app/renters": () => json(RENTERS),
    "/api/app/properties": () => json([PROPERTY]),
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("collections panel", () => {
  test("puts overdue leases first and shows what is due by month end", async () => {
    mockHome();
    await renderPage("/app");

    expect(await screen.findByText("Por cobrar hasta fin de mes: S/ 2,700.00")).toBeDefined();
    expect(screen.getByText("De eso, S/ 1,100.00 ya está atrasado.")).toBeDefined();
    const overdue = screen.getByRole("region", { name: "Atrasados" });
    const names = within(overdue)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(names).toEqual([
      expect.stringContaining("Rosa Huamán"),
      expect.stringContaining("Ana Quispe"),
    ]);
    expect(within(overdue).getByText("Debe S/ 300.00 · 1 día de atraso")).toBeDefined();
    expect(within(overdue).getByText("Contrato terminado")).toBeDefined();
    expect(within(overdue).getByText("Debe S/ 800.00 · 52 días de atraso")).toBeDefined();
    const soon = screen.getByRole("region", { name: "Por vencer" });
    expect(within(soon).getByText("S/ 800.00 vence el 29/10/2026")).toBeDefined();
    expect(within(soon).getByText("Cuarto 2 · Casa de Surco")).toBeDefined();
    expect(screen.queryByRole("region", { name: "Vencen hoy" })).toBeNull();
  });

  test("says when each lease that owes was last reminded", async () => {
    mockHome(COLLECTIONS, [
      { lease_id: LEASES[0]?.id, sent_on: "2026-10-27", days_ago: 0 },
      { lease_id: LEASES[1]?.id, sent_on: "2026-10-26", days_ago: 1 },
      { lease_id: LEASES[2]?.id, sent_on: "2026-10-20", days_ago: 7 },
    ]);
    await renderPage("/app");

    const overdue = within(await screen.findByRole("region", { name: "Atrasados" }));
    expect(await overdue.findByText("Recordado hoy")).toBeDefined();
    expect(overdue.getByText("Recordado hace 7 días")).toBeDefined();
    expect(within(screen.getByRole("region", { name: "Por vencer" })).getByText("Recordado ayer"))
      .toBeDefined();
  });

  test("opens WhatsApp with the message from an overdue line", async () => {
    const tab = { opener: {}, location: { href: "" }, close: vi.fn() };
    vi.stubGlobal("open", vi.fn(() => tab));
    const path = `/api/app/leases/${String(LEASES[0]?.id)}/whatsapp-reminders`;
    const url = "https://wa.me/51987654321?text=Hola%20Ana";
    const api = mockApi({
      "/api/app/me": () => json(ME),
      "/api/app/collections": () => json(COLLECTIONS),
      "/api/app/whatsapp-reminders": () => json([]),
      "/api/app/leases": () => json(LEASES),
      "/api/app/renters": () => json(RENTERS),
      "/api/app/properties": () => json([PROPERTY]),
      [path]: () =>
        json(
          { kind: "overdue", charge_id: "0195a0b0-0000-7000-8000-000000000099", message: "Hola Ana", url },
          201,
        ),
    });
    await renderPage("/app");

    await userEvent.click(
      await screen.findByRole("button", { name: "Enviar por WhatsApp a Ana Quispe" }),
    );

    await vi.waitFor(() => {
      expect(tab.location.href).toBe(url);
    });
    expect(tab.opener).toBeNull();
    expect(api.requestsTo(path)[0]?.method).toBe("POST");
    await vi.waitFor(() => {
      expect(api.requestsTo("/api/app/whatsapp-reminders").length).toBe(2);
    });
  });

  test("explains why a lease can't be reminded and closes the tab it opened", async () => {
    const tab = { opener: {}, location: { href: "" }, close: vi.fn() };
    vi.stubGlobal("open", vi.fn(() => tab));
    mockApi({
      "/api/app/me": () => json(ME),
      "/api/app/collections": () => json(COLLECTIONS),
      "/api/app/whatsapp-reminders": () => json([]),
      "/api/app/leases": () => json(LEASES),
      "/api/app/renters": () => json(RENTERS),
      "/api/app/properties": () => json([PROPERTY]),
      [`/api/app/leases/${String(LEASES[0]?.id)}/whatsapp-reminders`]: () =>
        json({ detail: "whatsapp_unavailable" }, 403),
    });
    await renderPage("/app");

    await userEvent.click(
      await screen.findByRole("button", { name: "Enviar por WhatsApp a Ana Quispe" }),
    );

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "Este contrato no tiene WhatsApp ni enlace del inquilino en tu plan actual.",
    );
    expect(tab.close).toHaveBeenCalled();
    expect(tab.location.href).toBe("");
  });

  test("tells due today, the next charge and money in favor apart", async () => {
    const [first, second, third] = COLLECTIONS.leases;
    mockHome({
      due_by_month_end_cents: 50000,
      overdue_cents: 0,
      leases: [
        {
          ...first,
          ended: false,
          status: "due_today",
          next_due_on: "2026-10-27",
          next_due_cents: 50000,
        },
        { ...second, status: "up_to_date", next_due_on: "2026-11-05" },
        { ...third, status: "up_to_date", next_due_on: null, balance_cents: -2000 },
      ],
    });
    await renderPage("/app");

    expect(await screen.findByText("Hoy vence S/ 500.00")).toBeDefined();
    expect(screen.queryByText(/ya está atrasado/)).toBeNull();
    const upToDate = screen.getByRole("region", { name: "Al día" });
    expect(within(upToDate).getByText("Próximo cobro: S/ 800.00 el 05/11/2026")).toBeDefined();
    expect(within(upToDate).getByText("Tiene S/ 20.00 a favor")).toBeDefined();
  });

  test("opens a lease's charges from the panel", async () => {
    mockApi({
      "/api/app/me": () => json(ME),
      "/api/app/collections": () => json(COLLECTIONS),
      "/api/app/whatsapp-reminders": () => json([]),
      "/api/app/leases": () => json(LEASES),
      "/api/app/renters": () => json(RENTERS),
      "/api/app/properties": () => json([PROPERTY]),
      [`/api/app/leases/${String(LEASES[0]?.id)}/tenant-link`]: () => json({ link: null }),
      [`/api/app/leases/${String(LEASES[0]?.id)}/statement`]: () =>
        json({
          lease_id: LEASES[0]?.id,
          balance_cents: 160000,
          credit_cents: 0,
          up_to_date: false,
          charges: [],
          payments: [],
        }),
    });
    await renderPage("/app");

    await userEvent.click(await screen.findByRole("link", { name: /Ana Quispe/ }));

    expect(await screen.findByText("Te debe S/ 1,600.00")).toBeDefined();
  });

  test("invites a landlord without leases to register one", async () => {
    mockHome({ due_by_month_end_cents: 0, overdue_cents: 0, leases: [] });
    await renderPage("/app");

    expect(await screen.findByText(/aquí verás quién te debe/)).toBeDefined();
    expect(screen.getByRole("link", { name: "Registrar un contrato" })).toHaveProperty(
      "pathname",
      "/app/contratos/nuevo",
    );
  });
});
