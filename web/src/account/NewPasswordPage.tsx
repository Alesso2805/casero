import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Link, useLocation } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "../api/client";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { PasswordField, primaryButton } from "./fields";
import { hashToken } from "./hashToken";

const MIN_PASSWORD_LENGTH = 10;

const schema = z.object({
  password: z.string().min(MIN_PASSWORD_LENGTH, text.errors.password).max(1024),
});

type NewPasswordValues = z.input<typeof schema>;
type Outcome = "done" | "invalid";

async function resetPassword(input: { token: string; password: string }): Promise<Outcome> {
  const { response } = await api.POST("/api/public/password-reset/confirm", { body: input });
  if (response.status === 204) {
    return "done";
  }
  if (response.status === 400) {
    return "invalid";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function NewPasswordPage() {
  const token = hashToken(useLocation().hash);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<NewPasswordValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({ mutationFn: resetPassword });

  let body;
  if (mutation.data === "done") {
    body = (
      <>
        <p role="status" className="rounded-lg bg-emerald-50 p-4 text-emerald-900">
          {text.newPassword.done}
        </p>
        <Link to="/ingresar" className={`${primaryButton} flex items-center justify-center`}>
          {text.newPassword.logIn}
        </Link>
      </>
    );
  } else if (!token || mutation.data === "invalid") {
    body = (
      <>
        <p role="alert">{text.newPassword.invalid}</p>
        <Link to="/recuperar" className="text-brand underline">
          {text.newPassword.askAgain}
        </Link>
      </>
    );
  } else {
    body = (
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(event) => {
          void handleSubmit((values) => {
            mutation.mutate({ token, password: values.password });
          })(event);
        }}
      >
        <PasswordField
          id="password"
          autoComplete="new-password"
          hint={text.fields.passwordHint}
          error={errors.password}
          registration={register("password")}
        />
        {mutation.isError && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
        <button type="submit" disabled={mutation.isPending} className={primaryButton}>
          {mutation.isPending ? text.newPassword.sending : text.newPassword.submit}
        </button>
      </form>
    );
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.newPassword.title}</h1>
      {body}
      <PublicFooter />
    </div>
  );
}
