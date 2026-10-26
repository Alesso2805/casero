import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "../api/client";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { primaryButton, TextField } from "./fields";

const schema = z.object({ email: z.email({ error: text.errors.email }) });

type ForgotValues = z.input<typeof schema>;

async function requestReset(values: ForgotValues): Promise<"sent" | "limited"> {
  const { response } = await api.POST("/api/public/password-reset", { body: values });
  if (response.status === 202) {
    return "sent";
  }
  if (response.status === 429) {
    return "limited";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function ForgotPasswordPage() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({ mutationFn: requestReset });

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.forgot.title}</h1>
      {mutation.data === "sent" ? (
        <p role="status" className="rounded-lg bg-emerald-50 p-4 text-emerald-900">
          {text.forgot.sent}
        </p>
      ) : (
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            void handleSubmit((values) => {
              mutation.mutate(values);
            })(event);
          }}
        >
          <p>{text.forgot.intro}</p>
          <TextField
            id="email"
            label={text.fields.email}
            type="email"
            autoComplete="email"
            error={errors.email}
            registration={register("email")}
          />
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
            {mutation.isPending ? text.forgot.sending : text.forgot.submit}
          </button>
        </form>
      )}
      <PublicFooter />
    </div>
  );
}
