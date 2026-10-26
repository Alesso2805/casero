import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { mockApi } from "../test/api";
import { renderPage } from "../test/render";

const UNSUBSCRIBE = "/api/public/unsubscribe";
const LINK = "/baja?u=01a175b4-8f38-727d-a7dc-40a7a7b30001&k=daily_digest&t=abc";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("unsubscribe page", () => {
  test("asks before unsubscribing and sends the link's parameters", async () => {
    const api = mockApi({ [UNSUBSCRIBE]: 204 });
    await renderPage(LINK);

    expect(await screen.findByText(/dejar de recibir el resumen diario/)).toBeDefined();
    expect(api.requestsTo(UNSUBSCRIBE)).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "Darme de baja" }));

    expect((await screen.findByRole("status")).textContent).toBe(
      "Listo. Ya no te enviaremos el resumen diario.",
    );
    const [request] = api.requestsTo(UNSUBSCRIBE);
    const query = new URL(request?.url ?? "").searchParams;
    expect(Object.fromEntries(query)).toEqual({
      u: "01a175b4-8f38-727d-a7dc-40a7a7b30001",
      k: "daily_digest",
      t: "abc",
    });
  });

  test("explains a broken or forged link", async () => {
    mockApi({ [UNSUBSCRIBE]: 403 });
    await renderPage(LINK);

    await userEvent.click(await screen.findByRole("button", { name: "Darme de baja" }));

    expect((await screen.findByRole("alert")).textContent).toContain("no es válido");
  });

  test("rejects a link without its parameters", async () => {
    mockApi({});
    await renderPage("/baja?k=daily_digest");

    expect((await screen.findByRole("alert")).textContent).toContain("no es válido");
    expect(screen.queryByRole("button", { name: "Darme de baja" })).toBeNull();
  });
});
