import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const WCAG_21_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const SUNAT_RUC = "20131312955";
const ANA_DNI = "45678912";
// A past month whose tax rules and schedule are loaded, so CI doesn't depend on the year's
// rules being published (they arrive each December; docs/ops/tax-config.md).
const MONTH = "2026-01";
const PAID_ON = "2026-01-15";
// The service worker is registered by the production build that CI serves through the edge.
const PRODUCTION_EDGE = (process.env.CASERO_E2E_URL ?? "https://localhost").startsWith("https");

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.length.toString()}`)).toEqual([]);
}

async function addLease(page: Page, unit: string, rent: string, renter: "new" | "existing") {
  await page.goto("/app/contratos/nuevo");
  await page.getByLabel("¿Qué unidad alquilas?").selectOption({ label: unit });
  if (renter === "new") {
    await page.getByLabel("Nombre completo del inquilino").fill("Ana Prueba");
    await page.getByLabel("Documento (opcional)").selectOption("dni");
    await page.getByLabel("Número del documento").fill(ANA_DNI);
  } else {
    await page.getByLabel("A un inquilino que ya registré").check();
    await page.getByLabel("Inquilino", { exact: true }).selectOption({ label: "Ana Prueba" });
  }
  await page.getByLabel("Alquiler mensual en soles").fill(rent);
  await page.getByLabel("¿Qué día del mes te paga?").fill("5");
  await page.getByLabel("Fecha de inicio del contrato").fill(`${MONTH}-01`);
  await page.getByLabel("¿Desde qué mes llevas el control en Casero?").selectOption(MONTH);
  await page.getByRole("button", { name: "Guardar contrato" }).click();
  await expect(page).toHaveURL(/\/app\/contratos$/);
}

async function recordPayment(page: Page, lease: number, amount: string) {
  await page.goto("/app/contratos");
  await page.getByRole("link", { name: "Ver cobros de Ana Prueba" }).nth(lease).click();
  await page.getByRole("button", { name: "Registrar pago" }).click();
  await page.getByLabel("Monto recibido en soles").fill(amount);
  await page.getByLabel("Fecha en que recibiste el dinero").fill(PAID_ON);
  await page.getByLabel("¿Cómo te pagó?").selectOption("yape");
  await page.getByRole("button", { name: "Guardar pago" }).click();
  await expect(page.getByText("Listo, guardamos el pago.")).toBeVisible();
}

function watchCsp(page: Page, blocked: string[]) {
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) {
      blocked.push(message.text());
    }
  });
}

test("a landlord registers, rents two rooms to one tenant and gets one 1683", async ({ page }) => {
  const blocked: string[] = [];
  watchCsp(page, blocked);

  await page.goto("/registro");
  await page.getByLabel("¿Cómo te llamamos?").fill("Casera de Prueba");
  await page.getByLabel("Tu correo electrónico").fill(`casera+${Date.now().toString()}@example.com`);
  await page.getByLabel("Contraseña", { exact: true }).fill("una clave bien larga");
  for (const box of await page.getByRole("checkbox").all()) {
    await box.check();
  }
  await page.getByRole("button", { name: "Crear mi cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Inicio" })).toBeVisible();
  await expectAccessible(page);

  await page.goto("/app/mis-datos");
  await page.getByLabel("RUC (puedes completarlo después)").fill(SUNAT_RUC);
  await page.getByRole("button", { name: "Guardar mis datos" }).click();
  await expect(page.getByText("Listo, guardamos tus datos.")).toBeVisible();

  await page.goto("/app/inmuebles/nuevo");
  await page.getByLabel("Nombre del inmueble").fill("Casa de Prueba");
  await page.getByLabel("Solo mío").check();
  await page.getByLabel("Nombre de la unidad 1").fill("Cuarto 1");
  await page.getByRole("button", { name: "Agregar otra unidad" }).click();
  await page.getByLabel("Nombre de la unidad 2").fill("Cuarto 2");
  await page.getByRole("button", { name: "Guardar inmueble" }).click();
  await expect(page).toHaveURL(/\/app\/inmuebles$/);

  await addLease(page, "Cuarto 1", "450.50", "new");
  await addLease(page, "Cuarto 2", "100.50", "existing");
  await recordPayment(page, 0, "450.50");
  await recordPayment(page, 1, "100.50");
  await expectAccessible(page);

  await page.getByRole("button", { name: "Crear enlace" }).click();
  const link = await page.locator("#tenant-link-url").inputValue();
  const tenant = await page.context().newPage();
  watchCsp(tenant, blocked);
  await tenant.goto(link);
  await expect(tenant.getByText(/Hola, Ana Prueba/)).toBeVisible();
  await expectAccessible(tenant);
  await tenant.close();

  await page.goto("/app/mensajes");
  await expect(page.getByLabel("Atraso")).toBeVisible();
  await expectAccessible(page);
  if (PRODUCTION_EDGE) {
    const active = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready;
      return registration.active !== null;
    });
    expect(active).toBe(true);
  }

  await page.goto("/app/impuestos");
  const shown = page.getByRole("heading", { name: /^Pagos recibidos en / });
  await expect(shown).toBeVisible();
  while ((await shown.textContent()) !== "Pagos recibidos en enero de 2026") {
    const before = (await shown.textContent()) ?? "";
    await page.getByRole("button", { name: "Mes anterior" }).click();
    await expect(shown).not.toHaveText(before);
  }
  await expect(page.getByText("Total del mes: S/ 28.00 en 1 Formulario 1683.")).toBeVisible();
  await expect(page.getByText("Vencen el 19/02/2026, según el último dígito de tu RUC.")).toBeVisible();
  const card = page.getByRole("listitem").filter({ hasText: "Ana Prueba" });
  await expect(card.getByText(SUNAT_RUC)).toBeVisible();
  await expect(card.getByText(ANA_DNI)).toBeVisible();
  await expect(card.getByText("S/ 551.00", { exact: true })).toBeVisible();
  await expect(card.getByText("S/ 28.00", { exact: true })).toBeVisible();
  await expectAccessible(page);

  expect(blocked).toEqual([]);
});
