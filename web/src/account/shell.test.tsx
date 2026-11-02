import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";

const LEASES_PAGE = {
  "/api/app/leases": () => json([]),
  "/api/app/renters": () => json([]),
  "/api/app/properties": () => json([]),
  "/api/app/lease-tools": () => json({ limit: 10, over_limit: false, leases: [] }),
};

function linkNames(nav: HTMLElement) {
  return within(nav)
    .getAllByRole("link")
    .map((link) => link.textContent);
}

async function menus() {
  const [tabs, side] = (await screen.findAllByRole("navigation", { name: "Principal" })).sort(
    (first, second) => first.querySelectorAll("a").length - second.querySelectorAll("a").length,
  );
  if (!tabs || !side) {
    throw new Error("Expected the tabs and the side menu");
  }
  return { tabs, side };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("app navigation", () => {
  test("offers the four tabs and the full side menu", async () => {
    mockApi({});
    await renderPage("/app/mas");

    const { tabs, side } = await menus();
    expect(linkNames(tabs)).toEqual(["Inicio", "Contratos", "SUNAT", "Más"]);
    expect(linkNames(side)).toEqual([
      "Inicio",
      "Mis inmuebles",
      "Mis contratos",
      "Formularios de SUNAT",
      "Mensajes de cobro",
      "Mi plan",
      "Mis datos",
    ]);
  });

  test("marks the section of the page in both menus", async () => {
    mockApi(LEASES_PAGE);
    await renderPage("/app/contratos");

    const { tabs, side } = await menus();
    expect(within(tabs).getByRole("link", { name: "Contratos" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(within(tabs).getByRole("link", { name: "Inicio" }).getAttribute("aria-current")).toBeNull();
    expect(
      within(side).getByRole("link", { name: "Mis contratos" }).getAttribute("aria-current"),
    ).toBe("page");
  });

  test("the pages that live under Más keep that tab marked", async () => {
    mockApi({});
    await renderPage("/app/mas");
    const { tabs } = await menus();

    expect(within(tabs).getByRole("link", { name: "Más" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("heading", { name: "Más" })).toBeDefined();
    const more = screen.getByRole("navigation", { name: "Más" });
    expect(linkNames(more)).toEqual(["Mis inmuebles", "Mensajes de cobro", "Mi plan", "Mis datos"]);
  });

  test("logs out from the side menu", async () => {
    const api = mockApi({ "/api/app/session": 204 });
    await renderPage("/app/mas");

    const { side } = await menus();
    const menu = side.closest("aside");
    if (!menu) {
      throw new Error("Expected the side menu");
    }
    await userEvent.click(within(menu).getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Ingresa a Casero" })).toBeDefined();
    expect(api.requestsTo("/api/app/session")[0]?.method).toBe("DELETE");
  });
});
