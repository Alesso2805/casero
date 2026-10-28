import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "./test/api";
import { renderPage } from "./test/render";

const STACK =
  "TypeError: x is undefined\n    at Card (https://casero.example/assets/index-abc.js:1:2048)\n    at render";

async function freshReporter() {
  vi.resetModules();
  return import("./errors");
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("error reports", () => {
  test("carry the error type, the route and the code location, never the fragment", async () => {
    const api = mockApi({ "/api/public/client-errors": () => new Response(null, { status: 204 }) });
    window.history.replaceState({}, "", "/i#t=secret-token");
    const { reportError } = await freshReporter();
    const error = new TypeError("Ana Quispe");
    error.stack = STACK;

    reportError(error);

    await vi.waitFor(() => {
      expect(api.requestsTo("/api/public/client-errors")).toHaveLength(1);
    });
    const [request] = api.requestsTo("/api/public/client-errors");
    const body = await request?.text();
    expect(JSON.parse(body ?? "{}")).toEqual({
      name: "TypeError",
      route: "/i",
      where: "/assets/index-abc.js:1:2048",
    });
    expect(body).not.toContain("secret-token");
    expect(body).not.toContain("Ana Quispe");
  });

  test("stop after five per page", async () => {
    const api = mockApi({ "/api/public/client-errors": () => new Response(null, { status: 204 }) });
    const { reportError } = await freshReporter();

    for (let index = 0; index < 8; index += 1) {
      reportError(new Error("boom"));
    }

    await vi.waitFor(() => {
      expect(api.requestsTo("/api/public/client-errors")).toHaveLength(5);
    });
  });

  test("a code location keeps only the script path, line and column", async () => {
    const { codeLocation } = await freshReporter();

    expect(codeLocation(STACK)).toBe("/assets/index-abc.js:1:2048");
    expect(codeLocation("at x (https://casero.example/assets/a.js?v=1:3:4)")).toBe(
      "/assets/a.js:3:4",
    );
    expect(codeLocation(undefined)).toBeUndefined();
  });
});

describe("error pages", () => {
  test("an unknown address shows a Spanish page with a way home", async () => {
    mockApi({ "/api/public/business": () => json({}) });
    await renderPage("/no-existe");

    expect(await screen.findByRole("heading", { name: "No encontramos esta página" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toBeDefined();
  });
});
