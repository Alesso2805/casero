import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi, testBusiness } from "../test/api";
import { renderPage } from "../test/render";

const TOKEN = "AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI";
const STATEMENT = {
  landlord_name: "Rosa Pérez",
  renter_name: "Ana",
  unit: "Cuarto 1 · Casa de Surco",
  balance_cents: 30000,
  credit_cents: 0,
  up_to_date: false,
  charges: [
    {
      kind: "rent",
      period: "2026-09",
      pre_2026: null,
      amount_cents: 80000,
      due_date: "2026-09-05",
      outstanding_cents: 30000,
      status: "overdue",
      partial: true,
      voided: false,
    },
  ],
  payments: [{ amount_cents: 50000, received_on: "2026-09-10", method: "yape", voided: false }],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("tenant portal", () => {
  test("shows the tenant's balance, history and how their data is used", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-27T15:00:00Z"));
    const api = mockApi({ "/api/tenant/statement": () => json(STATEMENT) });
    await renderPage(`/i#t=${TOKEN}`);

    expect(
      await screen.findByText("Hola, Ana. Alquilas Cuarto 1 · Casa de Surco a Rosa Pérez."),
    ).toBeDefined();
    expect(document.title).toBe("Tu cuenta de alquiler · Casero");
    expect(screen.getByText("Debes S/ 300.00")).toBeDefined();
    expect(screen.getByText("Setiembre de 2026")).toBeDefined();
    expect(screen.getByText("Atrasado 52 días")).toBeDefined();
    expect(screen.getByText("Pagaste S/ 500.00 de S/ 800.00")).toBeDefined();
    expect(screen.getByText("Yape")).toBeDefined();
    expect(
      await screen.findByText(new RegExp(`escribe a ${testBusiness.privacy_inbox}`)),
    ).toBeDefined();
    const [request] = api.requestsTo("/api/tenant/statement");
    expect(request?.headers.get("X-Tenant-Token")).toBe(TOKEN);
    expect(request?.url).not.toContain(TOKEN);
  });

  test("without the business contact the notice still says who to ask", async () => {
    mockApi({
      "/api/tenant/statement": () => json(STATEMENT),
      "/api/public/business": 503,
    });
    await renderPage(`/i#t=${TOKEN}`);

    expect(
      await screen.findByText(/Para pedir que se corrijan o se borren, habla con Rosa Pérez\.$/),
    ).toBeDefined();
    expect(screen.queryByText(/escribe a Rosa Pérez/)).toBeNull();
  });

  test("explains a link that no longer works", async () => {
    mockApi({ "/api/tenant/statement": () => json({ detail: "link_not_found" }, 404) });
    await renderPage(`/i#t=${TOKEN}`);

    expect(await screen.findByText(/Este enlace no funciona o ya venció/)).toBeDefined();
  });

  test("a link without its token asks for a new one without calling the API", async () => {
    const api = mockApi({});
    await renderPage("/i");

    expect(await screen.findByText(/Este enlace no funciona o ya venció/)).toBeDefined();
    expect(api.requestsTo("/api/tenant/statement")).toHaveLength(0);
  });
});
