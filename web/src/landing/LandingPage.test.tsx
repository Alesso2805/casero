import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { renderPage } from "../test/render";

function respondWith(status: number) {
  const fetchMock = vi.fn(() => Promise.resolve(new Response(null, { status })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("landing page", () => {
  test("shows the promise and both plans", async () => {
    await renderPage("/");

    expect(await screen.findByRole("heading", { level: 1 })).toBeDefined();
    expect(screen.getByText("S/ 0")).toBeDefined();
    expect(screen.getByText("S/ 19 al mes o S/ 190 al año")).toBeDefined();
  });

  test("asks for a valid email and for consent before sending", async () => {
    const fetchMock = respondWith(202);
    await renderPage("/");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "no-es-un-correo");
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    expect(await screen.findByText("Ese correo parece incompleto. Revisa que tenga @ y un punto, por ejemplo: nombre@gmail.com.")).toBeDefined();
    expect(screen.getByText("Marca la casilla para que podamos escribirte.")).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("joins the waitlist with consent", async () => {
    const fetchMock = respondWith(202);
    await renderPage("/");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    expect(await screen.findByRole("status")).toBeDefined();
    const [request] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(new URL(request.url).pathname).toBe("/api/public/waitlist");
    expect(await request.json()).toEqual({
      email: "ana@example.com",
      consent: true,
      source: "landing",
    });
  });

  test("explains when there were too many attempts", async () => {
    respondWith(429);
    await renderPage("/");

    await userEvent.type(await screen.findByLabelText("Tu correo electrónico"), "ana@example.com");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Avisarme" }));

    expect((await screen.findByRole("alert")).textContent).toContain("muchos intentos");
  });
});

describe("privacy page", () => {
  test("renders the short privacy policy", async () => {
    await renderPage("/privacidad");

    expect(
      await screen.findByRole("heading", { name: "Política de privacidad de Casero (versión corta)" }),
    ).toBeDefined();
  });
});
