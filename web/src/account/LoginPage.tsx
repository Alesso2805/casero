import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "../api/client";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { PasswordField, primaryButton, TextField } from "./fields";

const schema = z.object({
  email: z.email({ error: text.errors.email }),
  password: z.string().min(1, text.errors.required).max(1024),
});

type LoginValues = z.input<typeof schema>;
type Outcome = "signed_in" | "invalid" | "limited";

async function logIn(values: LoginValues): Promise<Outcome> {
  const { response } = await api.POST("/api/public/session", { body: values });
  if (response.status === 204) {
    return "signed_in";
  }
  if (response.status === 401) {
    return "invalid";
  }
  if (response.status === 429) {
    return "limited";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function LoginPage() {
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: logIn,
    onSuccess: (outcome) => {
      if (outcome === "signed_in") {
        void navigate({ to: "/app" });
      }
    },
  });

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.login.title}</h1>
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(event) => {
          void handleSubmit((values) => {
            mutation.mutate(values);
          })(event);
        }}
      >
        <TextField
          id="email"
          label={text.fields.email}
          type="email"
          autoComplete="email"
          error={errors.email}
          registration={register("email")}
        />
        <PasswordField
          id="password"
          autoComplete="current-password"
          error={errors.password}
          registration={register("password")}
        />
        {mutation.data === "invalid" && (
          <p role="alert" className="text-red-800">
            {text.errors.invalidLogin}
          </p>
        )}
        {mutation.data === "limited" && (
          <p role="alert" className="text-red-800">
            {text.errors.tooManyAttempts}
          </p>
        )}
        {mutation.isError && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
        <button type="submit" disabled={mutation.isPending} className={primaryButton}>
          {mutation.isPending ? text.login.sending : text.login.submit}
        </button>
      </form>
      <Link to="/recuperar" className="text-brand underline">
        {text.login.forgot}
      </Link>
      <p>{text.login.noAccount}</p>
      <PublicFooter />
    </div>
  );
}
