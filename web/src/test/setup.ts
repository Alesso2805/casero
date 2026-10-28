import { afterEach, expect } from "vitest";

import { configureValidation } from "../validation";
import { unmockedRequests } from "./api";

configureValidation();

afterEach(() => {
  expect(unmockedRequests.splice(0), "requests to routes the test did not mock").toEqual([]);
});
