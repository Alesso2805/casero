import { useMutation, useQuery } from "@tanstack/react-query";
import { Navigate } from "@tanstack/react-router";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { CollectionsPanel } from "../collections/CollectionsPanel";
import { DueNotice } from "../tax/DueNotice";
import { accountCopy as text } from "./copy";
import { secondaryButton } from "./fields";
import { fetchLegalStatus, isBlocked, LegalGate } from "./LegalGate";
import { LogOutButtons } from "./session";
import { TrialNotice } from "./TrialNotice";

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
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const legal = useQuery({
    queryKey: ["legal"],
    queryFn: fetchLegalStatus,
    enabled: Boolean(me.data),
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
      {legal.isPending && <p role="status">{text.home.loading}</p>}
      {isBlocked(legal.data) && (
        <>
          <LegalGate status={legal.data} />
          <LogOutButtons />
        </>
      )}
      {!legal.isPending && !isBlocked(legal.data) && (
        <>
          <TrialNotice />
          <DueNotice />
          <CollectionsPanel />
        </>
      )}
    </div>
  );
}
