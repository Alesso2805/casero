import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { json, mockApi } from "../test/api";
import { renderPage } from "../test/render";

const PATH = "/api/app/message-templates";
const DEFAULTS = {
  friendly:
    "Hola {inquilino}, te recuerdo que el {fecha} vence el alquiler de {periodo} por {monto}. Puedes ver tu detalle aquí: {enlace}. ¡Gracias!",
  due_today:
    "Hola {inquilino}, hoy vence el alquiler de {periodo} por {monto}. Tu detalle está aquí: {enlace}.",
  overdue:
    "Hola {inquilino}, el alquiler de {periodo} por {monto} está pendiente desde el {fecha}. ¿Me confirmas cuándo podrías pagarlo? Tu detalle: {enlace}.",
};
const EDITED = "Hola {inquilino}, sigue pendiente {monto} de {periodo}.";

function templates(overdue = DEFAULTS.overdue) {
  return Object.entries(DEFAULTS).map(([kind, body]) => ({
    kind,
    body: kind === "overdue" ? overdue : body,
    default_body: body,
  }));
}

function form(name: string): HTMLElement {
  const field = screen.getByLabelText(name);
  const container = field.closest("form");
  if (!container) {
    throw new Error(`No form for ${name}`);
  }
  return container;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Mensajes de cobro", () => {
  test("edits a message and saves it", async () => {
    let current = DEFAULTS.overdue;
    const api = mockApi({
      [PATH]: () => json(templates(current)),
      [`${PATH}/overdue`]: (request) => {
        current = EDITED;
        return request.method === "PUT"
          ? json({ kind: "overdue", body: EDITED, default_body: DEFAULTS.overdue })
          : json({}, 405);
      },
    });
    await renderPage("/app/mensajes");

    const atraso = await screen.findByLabelText("Atraso");
    expect(atraso).toHaveProperty("value", DEFAULTS.overdue);
    expect(screen.getByText("{enlace}")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Volver al mensaje original" })).toBeNull();
    await userEvent.clear(atraso);
    await userEvent.type(atraso, EDITED.replaceAll("{", "{{"));
    await userEvent.click(within(form("Atraso")).getByRole("button", { name: "Guardar mensaje" }));

    expect(await screen.findByText("Listo, guardamos el mensaje.")).toBeDefined();
    expect(await api.requestsTo(`${PATH}/overdue`)[0]?.json()).toEqual({ body: EDITED });
    expect(
      await within(form("Atraso")).findByRole("button", { name: "Volver al mensaje original" }),
    ).toBeDefined();
  });

  test("restores the original message", async () => {
    let current = EDITED;
    const api = mockApi({
      [PATH]: () => json(templates(current)),
      [`${PATH}/overdue`]: () => {
        current = DEFAULTS.overdue;
        return json({ kind: "overdue", body: current, default_body: DEFAULTS.overdue });
      },
    });
    await renderPage("/app/mensajes");

    await userEvent.click(
      await screen.findByRole("button", { name: "Volver al mensaje original" }),
    );

    expect(await screen.findByText("Listo, guardamos el mensaje.")).toBeDefined();
    expect(screen.getByLabelText("Atraso")).toHaveProperty("value", DEFAULTS.overdue);
    expect(await api.requestsTo(`${PATH}/overdue`)[0]?.json()).toEqual({
      body: DEFAULTS.overdue,
    });
  });

  test("says when a word between braces is not one Casero knows, or the text is empty", async () => {
    mockApi({
      [PATH]: () => json(templates()),
      [`${PATH}/friendly`]: () => json({ detail: "unknown_variable" }, 422),
    });
    await renderPage("/app/mensajes");

    const amable = await screen.findByLabelText("Recordatorio amable");
    const save = within(form("Recordatorio amable")).getByRole("button", {
      name: "Guardar mensaje",
    });
    await userEvent.clear(amable);
    await userEvent.click(save);
    expect(await screen.findByText("Escribe el mensaje.")).toBeDefined();
    await userEvent.type(amable, "Hola {{nombre}");
    await userEvent.click(save);

    expect(
      await screen.findByText("Usa solo las palabras entre llaves de la lista."),
    ).toBeDefined();
  });
});
