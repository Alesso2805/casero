import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "@tanstack/react-router";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { CollectionsPanel } from "../collections/CollectionsPanel";
import { DueNotice } from "../tax/DueNotice";
import { accountCopy as text } from "./copy";
import { primaryButton, secondaryButton, textLink } from "./fields";

type Me = components["schemas"]["MeResponse"];

const limaDay = new Intl.DateTimeFormat("es-PE", {
  timeZone: "America/Lima",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

async function fetchMe(): Promise<Me | null> {
  const { data, response } = await api.GET("/api/app/me");
  if (response.status === 401) {
    return null;
  }
  if (!data) {
    throw new Error(`Unexpected status ${String(response.status)}`);
  }
  return data;
}

const RESEND_MESSAGES: Record<number, string> = {
  202: text.home.resent,
  204: text.home.resent,
  422: text.home.resendSuppressed,
  429: text.home.resendLimited,
};

async function resendVerification(): Promise<string> {
  const { response } = await api.POST("/api/app/email-verification");
  return RESEND_MESSAGES[response.status] ?? text.home.resendFailed;
}

function VerificationNotice({ me }: { me: Me }) {
  const resend = useMutation({ mutationFn: resendVerification });
  if (me.email_verified || !me.verify_by) {
    return null;
  }
  const notice = me.blocked_until_verified
    ? text.home.blocked(me.email)
    : text.home.verify(me.email, limaDay.format(new Date(me.verify_by)));
  return (
    <section className="flex flex-col gap-3 rounded-lg bg-amber-50 p-4 text-amber-900">
      <p>{notice}</p>
      <button
        type="button"
        className={secondaryButton}
        disabled={resend.isPending}
        onClick={() => {
          resend.mutate();
        }}
      >
        {text.home.resend}
      </button>
      {resend.data && <p role="status">{resend.data}</p>}
      {resend.isError && <p role="alert">{text.home.resendFailed}</p>}
    </section>
  );
}

export function AppHome() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const logOut = useMutation({
    mutationFn: async (everywhere: boolean) => {
      await (everywhere
        ? api.DELETE("/api/app/sessions")
        : api.DELETE("/api/app/session"));
    },
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["me"] });
      void navigate({ to: "/ingresar" });
    },
  });

  if (me.data === null) {
    return <Navigate to="/ingresar" />;
  }
  if (!me.data) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10 text-base">
        {me.isError ? (
          <p role="alert" className="text-red-800">
            {text.home.failure}
          </p>
        ) : (
          <p role="status">{text.home.loading}</p>
        )}
      </div>
    );
  }
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.home.greeting}</h1>
      <VerificationNotice me={me.data} />
      <DueNotice />
      <CollectionsPanel />
      <Link to="/app/inmuebles" className={textLink}>
        {text.home.properties}
      </Link>
      <Link to="/app/contratos" className={textLink}>
        {text.home.leases}
      </Link>
      <Link to="/app/impuestos" className={textLink}>
        {text.home.declarations}
      </Link>
      <Link to="/app/mensajes" className={textLink}>
        {text.home.templates}
      </Link>
      <Link to="/app/mis-datos" className={textLink}>
        {text.home.profile}
      </Link>
      <div className="flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          className={primaryButton}
          disabled={logOut.isPending}
          onClick={() => {
            logOut.mutate(false);
          }}
        >
          {text.home.logOut}
        </button>
        <button
          type="button"
          className={secondaryButton}
          disabled={logOut.isPending}
          onClick={() => {
            logOut.mutate(true);
          }}
        >
          {text.home.logOutEverywhere}
        </button>
      </div>
    </div>
  );
}
