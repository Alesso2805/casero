import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { api } from "../api/client";
import type { components } from "../api/schema";
import { accountCopy as text } from "./copy";
import { primaryButton, TextField, textLink } from "./fields";
import { hasRucShape, isValidRuc, rucGroup } from "./ruc";

type Profile = components["schemas"]["ProfileResponse"];
type Loaded = { kind: "profile"; profile: Profile } | { kind: "login" } | { kind: "paused" };

const schema = z.object({
  displayName: z.string().trim().min(1, text.errors.required).max(120),
  taxpayerKind: z.enum(["person", "estate"]),
  ruc: z
    .string()
    .trim()
    .superRefine((ruc, context) => {
      if (ruc === "") {
        return;
      }
      if (!hasRucShape(ruc)) {
        context.addIssue({ code: "custom", message: text.profile.rucLength });
      } else if (!isValidRuc(ruc)) {
        context.addIssue({ code: "custom", message: text.profile.rucInvalid });
      }
    }),
  goodTaxpayer: z.boolean(),
  dailyDigest: z.boolean(),
  taxReminders: z.boolean(),
});

type ProfileValues = z.input<typeof schema>;

export async function fetchProfile(): Promise<Loaded> {
  const { data, response } = await api.GET("/api/app/account/profile");
  if (data) {
    return { kind: "profile", profile: data };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return { kind: "paused" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

async function saveProfile(values: ProfileValues): Promise<Profile | "invalid_ruc"> {
  const ruc = values.ruc.trim();
  const { data, response } = await api.PUT("/api/app/account/profile", {
    body: {
      display_name: values.displayName,
      taxpayer_kind: values.taxpayerKind,
      ruc: ruc === "" ? null : ruc,
      good_taxpayer: ruc !== "" && values.goodTaxpayer,
      daily_digest: values.dailyDigest,
      tax_reminders_email: values.taxReminders,
    },
  });
  if (data) {
    return data;
  }
  if (response.status === 422) {
    return "invalid_ruc";
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

function groupMessage(ruc: string, goodTaxpayer: boolean): string {
  const group = rucGroup(ruc, goodTaxpayer);
  if (group === null) {
    return text.profile.noRuc;
  }
  return group === "bc"
    ? text.profile.goodTaxpayerGroup
    : text.profile.digitGroup(text.profile.groupDigits[group]);
}

const checkbox = "mt-1 size-6 shrink-0";

function ProfileForm({ profile }: { profile: Profile }) {
  const queryClient = useQueryClient();
  const {
    register: field,
    control,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ProfileValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      displayName: profile.display_name,
      taxpayerKind: profile.taxpayer_kind,
      ruc: profile.ruc ?? "",
      goodTaxpayer: profile.ruc_group === "bc",
      dailyDigest: profile.daily_digest,
      taxReminders: profile.tax_reminders_email,
    },
  });
  const [ruc, goodTaxpayer, taxpayerKind] = useWatch({
    control,
    name: ["ruc", "goodTaxpayer", "taxpayerKind"],
  });
  const mutation = useMutation({
    mutationFn: saveProfile,
    onSuccess: (result) => {
      if (result === "invalid_ruc") {
        setError("ruc", { message: text.profile.rucInvalid });
      } else {
        const saved: Loaded = { kind: "profile", profile: result };
        queryClient.setQueryData(["profile"], saved);
      }
    },
  });
  const trimmedRuc = ruc.trim();

  return (
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
        id="display-name"
        label={text.profile.displayName}
        autoComplete="name"
        hint={text.profile.displayNameHint}
        error={errors.displayName}
        registration={field("displayName")}
      />
      {profile.declarant_locked ? (
        <div className="flex flex-col gap-1">
          <p className="text-base font-medium">{text.profile.taxpayerKind}</p>
          <p>{taxpayerKind === "estate" ? text.profile.estate : text.profile.person}</p>
          <p className="text-base text-stone-600">{text.profile.declarantLocked}</p>
        </div>
      ) : (
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 text-base font-medium">{text.profile.taxpayerKind}</legend>
          <label className="flex min-h-11 items-center gap-3">
            <input type="radio" value="person" className="size-6" {...field("taxpayerKind")} />
            {text.profile.person}
          </label>
          <label className="flex min-h-11 items-center gap-3">
            <input type="radio" value="estate" className="size-6" {...field("taxpayerKind")} />
            {text.profile.estate}
          </label>
          {taxpayerKind === "estate" && (
            <p className="text-base text-stone-600">{text.profile.estateHint}</p>
          )}
        </fieldset>
      )}
      <TextField
        id="ruc"
        label={text.profile.ruc}
        numeric
        autoComplete="off"
        hint={taxpayerKind === "estate" ? text.profile.rucEstate : text.profile.rucPerson}
        error={errors.ruc}
        registration={field("ruc")}
      />
      {trimmedRuc !== "" && (
        <div className="flex flex-col gap-1">
          <div className="flex items-start gap-3">
            <input
              id="good-taxpayer"
              type="checkbox"
              className={checkbox}
              aria-describedby="good-taxpayer-hint"
              {...field("goodTaxpayer")}
            />
            <label htmlFor="good-taxpayer">{text.profile.goodTaxpayer}</label>
          </div>
          <p id="good-taxpayer-hint" className="text-base text-stone-600">
            {text.profile.goodTaxpayerHint}
          </p>
        </div>
      )}
      <p className="rounded-lg bg-stone-100 p-4">{groupMessage(trimmedRuc, goodTaxpayer)}</p>
      <div className="flex flex-col gap-1">
        <div className="flex items-start gap-3">
          <input
            id="tax-reminders"
            type="checkbox"
            className={checkbox}
            aria-describedby="tax-reminders-hint"
            {...field("taxReminders")}
          />
          <label htmlFor="tax-reminders">{text.profile.taxReminders}</label>
        </div>
        <p id="tax-reminders-hint" className="text-base text-stone-600">
          {text.profile.taxRemindersHint}
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <div className="flex items-start gap-3">
          <input
            id="daily-digest"
            type="checkbox"
            className={checkbox}
            aria-describedby="daily-digest-hint"
            {...field("dailyDigest")}
          />
          <label htmlFor="daily-digest">{text.profile.dailyDigest}</label>
        </div>
        <p id="daily-digest-hint" className="text-base text-stone-600">
          {text.profile.dailyDigestHint}
        </p>
      </div>
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      {mutation.isSuccess && mutation.data !== "invalid_ruc" && (
        <p role="status" className="text-green-800">
          {text.profile.saved}
        </p>
      )}
      <button type="submit" disabled={mutation.isPending} className={primaryButton}>
        {mutation.isPending ? text.profile.sending : text.profile.submit}
      </button>
    </form>
  );
}

export function ProfilePage() {
  const loaded = useQuery({ queryKey: ["profile"], queryFn: fetchProfile });

  if (loaded.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.profile.title}</h1>
      {loaded.data?.kind === "paused" && <p role="alert">{text.profile.paused}</p>}
      {loaded.data?.kind === "profile" && <ProfileForm profile={loaded.data.profile} />}
      {loaded.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
      <Link to="/app" className={textLink}>
        {text.profile.back}
      </Link>
    </div>
  );
}
