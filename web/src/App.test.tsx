import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("shows the product name", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "Casero" })).toBeDefined();
});
