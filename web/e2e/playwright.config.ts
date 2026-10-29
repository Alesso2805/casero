import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "*.e2e.ts",
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  outputDir: "test-results",
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : "list",
  use: {
    // The production edge with `tls internal`, as CI starts it (Edge job).
    baseURL: process.env.CASERO_E2E_URL ?? "https://localhost",
    ignoreHTTPSErrors: true,
    locale: "es-PE",
    timezoneId: "America/Lima",
    trace: "retain-on-failure",
    ...devices["Pixel 7"],
  },
});
