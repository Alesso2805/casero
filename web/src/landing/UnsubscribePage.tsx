import { useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "@tanstack/react-router";

import { api } from "../api/client";
import { PublicFooter } from "./PublicFooter";

type EmailKind = "daily_digest" | "tax_reminders";
type Outcome = "done" | "invalid";

const text = {
  title: "Dejar de recibir correos",
  kinds: { daily_digest: "el resumen diario", tax_reminders: "los recordatorios de impuesto" },
  question: (kind: string) =>
    `¿Quieres dejar de recibir ${kind} de Casero? Seguirás recibiendo los correos necesarios de tu cuenta, como la recuperación de contraseña.`,
  confirm: "Darme de baja",
  sending: "Procesando…",
  done: (kind: string) => `Listo. Ya no te enviaremos ${kind}.`,
  invalid: "Este enlace no es válido. Usa el enlace del último correo que recibiste.",
  failure: "No pudimos procesar tu baja. Vuelve a intentarlo en unos minutos.",
  back: "Volver al inicio",
} as const;

interface UnsubscribeLink {
  u: string;
  k: EmailKind;
  t: string;
}

function readLink(search: string): UnsubscribeLink | null {
  const params = new URLSearchParams(search);
  const u = params.get("u");
  const k = params.get("k");
  const t = params.get("t");
  if (!u || !t || (k !== "daily_digest" && k !== "tax_reminders")) {
    return null;
  }
  return { u, k, t };
}

async function unsubscribe(link: UnsubscribeLink): Promise<Outcome> {
  const { response } = await api.POST("/api/public/unsubscribe", { params: { query: link } });
  if (response.status === 204) {
    return "done";
  }
  if (response.status === 403 || response.status === 422) {
    return "invalid";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function UnsubscribePage() {
  const { searchStr } = useLocation();
  const link = readLink(searchStr);
  const mutation = useMutation({ mutationFn: unsubscribe });

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.title}</h1>
      {!link || mutation.data === "invalid" ? (
        <p role="alert">{text.invalid}</p>
      ) : mutation.data === "done" ? (
        <p role="status" className="rounded-lg bg-emerald-50 p-4 text-emerald-900">
          {text.done(text.kinds[link.k])}
        </p>
      ) : (
        <>
          <p>{text.question(text.kinds[link.k])}</p>
          {mutation.isError && (
            <p role="alert" className="text-red-800">
              {text.failure}
            </p>
          )}
          <button
            type="button"
            disabled={mutation.isPending}
            className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
            onClick={() => {
              mutation.mutate(link);
            }}
          >
            {mutation.isPending ? text.sending : text.confirm}
          </button>
        </>
      )}
      <Link to="/" className="text-brand underline">
        {text.back}
      </Link>
      <PublicFooter />
    </div>
  );
}
