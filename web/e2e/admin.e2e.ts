import { createHmac } from "node:crypto";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const WCAG_21_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const ADMIN_URL = process.env.CASERO_E2E_ADMIN_URL ?? "";
const STAFF_EMAIL = process.env.CASERO_E2E_STAFF_EMAIL ?? "";
const STAFF_PASSWORD = process.env.CASERO_E2E_STAFF_PASSWORD ?? "";
const TOTP_URI = process.env.CASERO_E2E_TOTP_URI ?? "";
const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
const TOTP_STEP_MS = 30_000;

function totpCode(): string {
  const secret = new URL(TOTP_URI).searchParams.get("secret") ?? "";
  const bits = Array.from(secret, (letter) =>
    BASE32.indexOf(letter).toString(2).padStart(5, "0"),
  );
  const bytes = (bits.join("").match(/.{8}/g) ?? []).map((byte) => parseInt(byte, 2));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / TOTP_STEP_MS)));
  const digest = createHmac("sha1", Buffer.from(bytes)).update(counter).digest();
  const offset = (digest.at(-1) ?? 0) & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.length.toString()}`)).toEqual([]);
}

async function registerLandlord(page: Page, email: string) {
  await page.goto("/registro");
  await page.getByLabel("¿Cómo te llamamos?").fill("Casera de Prueba");
  await page.getByLabel("Tu correo electrónico").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill("una clave bien larga");
  for (const box of await page.getByRole("checkbox").all()) {
    await box.check();
  }
  await page.getByRole("button", { name: "Crear mi cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Inicio" })).toBeVisible();
  // Here the site and the panel share the host `localhost`; on the server they never do.
  await page.context().clearCookies();
}

test.skip(!ADMIN_URL, "needs CASERO_E2E_ADMIN_URL of a running panel");

test("the owner logs in, finds an account and records its Yape payment", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(String(error)));
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) {
      problems.push(message.text());
    }
  });
  const landlord = `casera-${Date.now().toString()}@example.com`;
  await registerLandlord(page, landlord);

  await page.goto(`${ADMIN_URL}/admin`);
  await expect(page).toHaveURL(/\/admin\/ingresar$/);
  await expectAccessible(page);
  await page.getByLabel("Correo").fill(STAFF_EMAIL);
  await page.getByLabel("Contraseña").fill(STAFF_PASSWORD);
  await page.getByLabel("Código de tu app de autenticación").fill(totpCode());
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByRole("heading", { name: "Cuentas" })).toBeVisible();
  await expectAccessible(page);

  await page.getByLabel("Correo de la cuenta").fill(landlord);
  await page.getByRole("button", { name: "Buscar" }).click();
  await page.getByRole("link", { name: landlord }).click();
  await expect(page.getByRole("heading", { name: landlord })).toBeVisible();
  await expect(page.getByText("Aún no hay pagos registrados.")).toBeVisible();
  await expectAccessible(page);

  await page.getByLabel("Monto en soles").fill("19");
  await page.getByLabel("Número de boleta").fill("EB01-1");
  await page.getByRole("button", { name: "Registrar pago" }).click();
  await expect(page.getByText("Pago registrado.")).toBeVisible();
  await expect(page.getByText(/S\/ 19\.00.*EB01-1/)).toBeVisible();

  await page.getByRole("link", { name: "Cronograma de SUNAT" }).click();
  await expect(page.getByRole("heading", { name: "Cronograma de SUNAT" })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expectAccessible(page);

  await page.getByRole("link", { name: "Reclamos" }).click();
  await expect(page.getByRole("heading", { name: "Reclamos" })).toBeVisible();
  await expectAccessible(page);

  await page.getByRole("button", { name: "Salir" }).click();
  await expect(page).toHaveURL(/\/admin\/ingresar$/);
  await page.goto(`${ADMIN_URL}/admin`);
  await expect(page).toHaveURL(/\/admin\/ingresar$/);
  expect(problems).toEqual([]);
});
