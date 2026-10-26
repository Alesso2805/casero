import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useBusiness } from "../api/business";
import { api } from "../api/client";
import { copy } from "./copy";

const text = copy.waitlist;

const schema = z.object({
  email: z.email({ error: text.invalidEmail }),
  consent: z.literal(true, { error: text.missingConsent }),
});

type WaitlistValues = z.input<typeof schema>;

type Outcome = "joined" | "limited";

async function joinWaitlist(email: string): Promise<Outcome> {
  const { response } = await api.POST("/api/public/waitlist", {
    body: { email, consent: true, source: "landing" },
  });
  if (response.status === 202) {
    return "joined";
  }
  if (response.status === 429) {
    return "limited";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

export function WaitlistForm() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<WaitlistValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({ mutationFn: joinWaitlist });
  const business = useBusiness();

  if (mutation.data === "joined") {
    return (
      <p role="status" className="rounded-lg bg-emerald-50 p-4 text-base text-emerald-900">
        {text.success}
      </p>
    );
  }

  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          mutation.mutate(values.email);
        })(event);
      }}
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="waitlist-email" className="text-base font-medium">
          {text.emailLabel}
        </label>
        <input
          id="waitlist-email"
          type="email"
          autoComplete="email"
          inputMode="email"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? "waitlist-email-error" : undefined}
          className="min-h-11 rounded-lg border border-stone-400 px-3 text-base"
          {...register("email")}
        />
        {errors.email && (
          <p id="waitlist-email-error" className="text-base text-red-800">
            {errors.email.message}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-start gap-3">
          <input
            id="waitlist-consent"
            type="checkbox"
            aria-invalid={errors.consent ? true : undefined}
            aria-describedby={errors.consent ? "waitlist-consent-error" : undefined}
            className="mt-1 size-6 shrink-0"
            {...register("consent")}
          />
          <label htmlFor="waitlist-consent" className="text-base">
            {text.consentLabel(business.data?.name ?? text.controllerFallback)}{" "}
            <Link to="/privacidad" className="text-brand underline">
              {text.privacyLink}
            </Link>
          </label>
        </div>
        {errors.consent && (
          <p id="waitlist-consent-error" className="text-base text-red-800">
            {errors.consent.message}
          </p>
        )}
      </div>
      {mutation.data === "limited" && (
        <p role="alert" className="text-base text-red-800">
          {text.tooManyAttempts}
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="text-base text-red-800">
          {text.failure}
        </p>
      )}
      <button
        type="submit"
        disabled={mutation.isPending}
        className="min-h-11 rounded-lg bg-brand px-5 text-base font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
      >
        {mutation.isPending ? text.sending : text.submit}
      </button>
    </form>
  );
}
