import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useBusiness } from "../api/business";
import { api } from "../api/client";
import { PublicFooter } from "../landing/PublicFooter";
import { accountCopy as text } from "./copy";
import { ErrorText, PasswordField, primaryButton, TextField } from "./fields";

const MIN_PASSWORD_LENGTH = 10;

const schema = z.object({
  displayName: z.string().trim().min(1, text.errors.required).max(120),
  email: z.email({ error: text.errors.email }),
  password: z.string().min(MIN_PASSWORD_LENGTH, text.errors.password).max(1024),
  acceptTerms: z.literal(true, { error: text.errors.terms }),
  consent: z.literal(true, { error: text.errors.consent }),
});

type RegisterValues = z.input<typeof schema>;
type Outcome = "created" | "invite" | "taken" | "limited";

const OUTCOMES: Record<number, Outcome> = {
  201: "created",
  403: "invite",
  409: "taken",
  429: "limited",
};

function inviteToken(hash: string): string | null {
  return new URLSearchParams(hash.replace(/^#/, "")).get("invitacion");
}

async function register(values: RegisterValues & { invite: string | null }): Promise<Outcome> {
  const { response } = await api.POST("/api/public/registration", {
    body: {
      email: values.email,
      password: values.password,
      display_name: values.displayName,
      invite_token: values.invite,
      accept_terms_and_privacy: true,
      consent_sensitive_data: true,
    },
  });
  const outcome = OUTCOMES[response.status];
  if (!outcome) {
    throw new Error(`Unexpected status ${String(response.status)}`);
  }
  return outcome;
}

const SERVER_ERRORS: Record<Exclude<Outcome, "created">, string> = {
  invite: text.errors.invite,
  taken: text.errors.taken,
  limited: text.errors.tooManyAttempts,
};

export function RegisterPage() {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const business = useBusiness();
  const {
    register: field,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: register,
    onSuccess: (outcome) => {
      if (outcome === "created") {
        void navigate({ to: "/app" });
      }
    },
  });
  const outcome = mutation.data;

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.register.title}</h1>
      <p>{text.register.inviteNotice}</p>
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={(event) => {
          void handleSubmit((values) => {
            mutation.mutate({ ...values, invite: inviteToken(hash) });
          })(event);
        }}
      >
        <TextField
          id="display-name"
          label={text.fields.displayName}
          autoComplete="name"
          error={errors.displayName}
          registration={field("displayName")}
        />
        <TextField
          id="email"
          label={text.fields.email}
          type="email"
          autoComplete="email"
          error={errors.email}
          registration={field("email")}
        />
        <PasswordField
          id="password"
          autoComplete="new-password"
          hint={text.fields.passwordHint}
          error={errors.password}
          registration={field("password")}
        />
        <div className="flex flex-col gap-1">
          <div className="flex items-start gap-3">
            <input
              id="accept-terms"
              type="checkbox"
              className="mt-1 size-6 shrink-0"
              aria-invalid={errors.acceptTerms ? true : undefined}
              aria-describedby={errors.acceptTerms ? "accept-terms-error" : undefined}
              {...field("acceptTerms")}
            />
            <label htmlFor="accept-terms">
              {text.register.acceptTerms}{" "}
              <a href="/legal/terminos" target="_blank" className="text-brand underline">
                {text.register.terms}
              </a>{" "}
              {text.register.and}{" "}
              <a href="/legal/privacidad" target="_blank" className="text-brand underline">
                {text.register.privacy}
              </a>
              .
            </label>
          </div>
          <ErrorText id="accept-terms" error={errors.acceptTerms} />
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-start gap-3">
            <input
              id="consent"
              type="checkbox"
              className="mt-1 size-6 shrink-0"
              aria-invalid={errors.consent ? true : undefined}
              aria-describedby={errors.consent ? "consent-error" : undefined}
              {...field("consent")}
            />
            <label htmlFor="consent">
              {text.register.consent(business.data?.name ?? text.register.controllerFallback)}{" "}
              <a
                href="/legal/consentimiento-datos-sensibles"
                target="_blank"
                className="text-brand underline"
              >
                {text.register.consentLink}
              </a>
              .
            </label>
          </div>
          <ErrorText id="consent" error={errors.consent} />
        </div>
        {outcome && outcome !== "created" && (
          <p role="alert" className="text-red-800">
            {SERVER_ERRORS[outcome]}
          </p>
        )}
        {mutation.isError && (
          <p role="alert" className="text-red-800">
            {text.errors.failure}
          </p>
        )}
        <button type="submit" disabled={mutation.isPending} className={primaryButton}>
          {mutation.isPending ? text.register.sending : text.register.submit}
        </button>
      </form>
      <p>
        {text.register.haveAccount}{" "}
        <Link to="/ingresar" className="text-brand underline">
          {text.register.logIn}
        </Link>
      </p>
      <PublicFooter />
    </div>
  );
}
