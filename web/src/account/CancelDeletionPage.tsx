import { useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "@tanstack/react-router";

import { useBusiness } from "../api/business";
import { api } from "../api/client";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { primaryButton, textLink } from "./fields";
import { hashToken } from "./hashToken";

type Outcome = "cancelled" | "invalid" | "taken";

async function cancelDeletion(token: string): Promise<Outcome> {
  const { response } = await api.POST("/api/public/account-deletion/cancellation", {
    body: { token },
  });
  if (response.status === 204) {
    return "cancelled";
  }
  if (response.status === 400 || response.status === 422) {
    return "invalid";
  }
  if (response.status === 409) {
    return "taken";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

/** Asks first, like /baja: mail filters open links, and this one can only be used once. */
export function CancelDeletionPage() {
  const token = hashToken(useLocation().hash);
  const business = useBusiness();
  const cancel = useMutation({ mutationFn: cancelDeletion });
  const inbox = business.data?.privacy_inbox ?? "";
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.cancelDeletion.title}</h1>
      {cancel.data === "cancelled" && <p role="status">{text.cancelDeletion.done}</p>}
      {(!token || cancel.data === "invalid") && <p role="alert">{text.cancelDeletion.invalid}</p>}
      {cancel.data === "taken" && <p role="alert">{text.cancelDeletion.taken(inbox)}</p>}
      {cancel.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {token && !cancel.data && (
        <>
          <p>{text.cancelDeletion.intro}</p>
          <button
            type="button"
            className={primaryButton}
            disabled={cancel.isPending}
            onClick={() => {
              cancel.mutate(token);
            }}
          >
            {text.cancelDeletion.confirm}
          </button>
        </>
      )}
      <Link to="/ingresar" className={textLink}>
        {text.cancelDeletion.login}
      </Link>
      <PublicFooter />
    </div>
  );
}
