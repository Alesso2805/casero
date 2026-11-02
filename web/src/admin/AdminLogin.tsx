import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PasswordField, primaryButton, TextField } from "../account/fields";
import { adminApi } from "./api";
import { adminCopy as text } from "./copy";

const schema = z.object({
  email: z.email({ error: text.login.emailError }),
  password: z.string().min(1, text.required).max(1024),
  code: z.string().trim().min(1, text.required).max(64),
});

type LoginValues = z.input<typeof schema>;

async function logIn(values: LoginValues): Promise<"signed_in" | "invalid"> {
  const { response } = await adminApi.POST("/api/admin/session", { body: values });
  if (response.status === 204) {
    return "signed_in";
  }
  if (response.status === 401) {
    return "invalid";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function AdminLogin() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: logIn,
    onSuccess: (outcome) => {
      if (outcome === "signed_in") {
        // The cached 401 that brought us here would send the shell straight back.
        queryClient.removeQueries({ queryKey: ["staff"] });
        void navigate({ to: "/" });
      }
    },
  });

  return (
    <main className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
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
          label={text.login.email}
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
        <TextField
          id="code"
          label={text.login.code}
          autoComplete="one-time-code"
          hint={text.login.codeHint}
          error={errors.code}
          registration={register("code")}
        />
        {mutation.data === "invalid" && (
          <p role="alert" className="text-red-800">
            {text.login.invalid}
          </p>
        )}
        {mutation.isError && (
          <p role="alert" className="text-red-800">
            {text.failure}
          </p>
        )}
        <button type="submit" disabled={mutation.isPending} className={primaryButton}>
          {text.login.submit}
        </button>
      </form>
    </main>
  );
}
