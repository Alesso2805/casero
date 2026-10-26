import { useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "@tanstack/react-router";
import { useEffect, useRef } from "react";

import { api } from "../api/client";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { primaryButton } from "./fields";
import { hashToken } from "./hashToken";

async function confirmEmail(token: string): Promise<boolean> {
  const { response } = await api.POST("/api/public/email-verification", { body: { token } });
  if (response.status === 204) {
    return true;
  }
  if (response.status === 400 || response.status === 422) {
    return false;
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function VerifyPage() {
  const token = hashToken(useLocation().hash);
  const { mutate, data, isError } = useMutation({ mutationFn: confirmEmail });
  const started = useRef(false);

  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      mutate(token);
    }
  }, [token, mutate]);

  let message;
  if (!token || data === false) {
    message = <p role="alert">{text.verify.invalid}</p>;
  } else if (data) {
    message = <p role="status">{text.verify.done}</p>;
  } else if (isError) {
    message = <p role="alert">{text.errors.failure}</p>;
  } else {
    message = <p>{text.verify.checking}</p>;
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.verify.title}</h1>
      {message}
      <Link to="/app" className={`${primaryButton} flex items-center justify-center`}>
        {text.verify.goToAccount}
      </Link>
      <PublicFooter />
    </div>
  );
}
