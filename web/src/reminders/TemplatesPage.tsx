import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { primaryButton, secondaryButton, textLink } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { leasesCopy } from "../leases/copy";
import { remindersCopy } from "./copy";

const text = remindersCopy.templates;

type Template = components["schemas"]["TemplateResponse"];
type Loaded = { kind: "templates"; templates: Template[] } | { kind: "login" } | { kind: "paused" };

// Mirrors MAX_BODY_LENGTH in casero.reminders.domain.messages; the server has the final word.
const MAX_BODY_LENGTH = 1000;

const schema = z.object({
  body: z.string().trim().min(1, text.errors.required).max(MAX_BODY_LENGTH, text.errors.tooLong),
});

type TemplateValues = z.input<typeof schema>;

async function fetchTemplates(): Promise<Loaded> {
  const { data, response } = await api.GET("/api/app/message-templates");
  if (data) {
    return { kind: "templates", templates: data };
  }
  if (response.status === 401) {
    return { kind: "login" };
  }
  if (response.status === 403) {
    return { kind: "paused" };
  }
  throw new Error(`Unexpected status ${String(response.status)}`);
}

async function saveTemplate(kind: Template["kind"], body: string): Promise<string | null> {
  const { data, error } = await api.PUT("/api/app/message-templates/{kind}", {
    params: { path: { kind } },
    body: { body },
  });
  if (data) {
    return null;
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return detail === "unknown_variable" ? text.errors.unknownVariable : text.errors.failure;
}

function TemplateForm({ template }: { template: Template }) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const id = `template-${template.kind}`;
  const {
    register,
    handleSubmit,
    setError,
    setValue,
    formState: { errors },
  } = useForm<TemplateValues>({
    resolver: zodResolver(schema),
    defaultValues: { body: template.body },
  });
  const save = useMutation({
    mutationFn: (body: string) => saveTemplate(template.kind, body.trim()),
    onMutate: () => {
      setSaved(false);
    },
    onSuccess: async (refusal) => {
      if (refusal) {
        setError("body", { message: refusal });
        return;
      }
      setSaved(true);
      await queryClient.invalidateQueries({ queryKey: ["message-templates"] });
    },
  });
  const kindText = text.kinds[template.kind];
  const describedBy = [`${id}-hint`, errors.body ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <form
      noValidate
      className="flex flex-col gap-3 rounded-lg border border-stone-300 p-4"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          save.mutate(values.body);
        })(event);
      }}
    >
      <label htmlFor={id} className="text-xl font-semibold">
        {kindText.title}
      </label>
      <p id={`${id}-hint`} className="text-stone-600">
        {kindText.when}
      </p>
      <textarea
        id={id}
        rows={5}
        aria-invalid={errors.body ? true : undefined}
        aria-describedby={describedBy}
        className="min-h-11 w-full rounded-lg border border-stone-400 px-3 py-2 text-base"
        {...register("body")}
      />
      {errors.body && (
        <p id={`${id}-error`} className="text-red-800">
          {errors.body.message}
        </p>
      )}
      <button type="submit" className={primaryButton} disabled={save.isPending}>
        {save.isPending ? text.saving : text.save}
      </button>
      {template.body !== template.default_body && (
        <button
          type="button"
          className={secondaryButton}
          disabled={save.isPending}
          onClick={() => {
            setValue("body", template.default_body);
            save.mutate(template.default_body);
          }}
        >
          {text.restore}
        </button>
      )}
      {saved && <p role="status">{text.saved}</p>}
      {save.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
    </form>
  );
}

export function TemplatesPage() {
  const loaded = useQuery({ queryKey: ["message-templates"], queryFn: fetchTemplates });

  if (loaded.data?.kind === "login") {
    return <Navigate to="/ingresar" />;
  }
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <h1 className="text-3xl font-bold">{text.title}</h1>
      <p>{text.intro}</p>
      <div className="flex flex-col gap-2">
        <p>{text.variables}</p>
        <ul className="flex flex-col gap-1 pl-2">
          {text.variableList.map(([variable, meaning]) => (
            <li key={variable}>
              <span className="font-semibold">{variable}</span>: {meaning}
            </li>
          ))}
        </ul>
      </div>
      {loaded.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {loaded.isPending && <p role="status">{text.loading}</p>}
      {loaded.data?.kind === "paused" && <p role="alert">{leasesCopy.errors.paused}</p>}
      {loaded.data?.kind === "templates" &&
        loaded.data.templates.map((template) => (
          <TemplateForm key={template.kind} template={template} />
        ))}
      <p className="text-stone-600">{remindersCopy.hint}</p>
      <Link to="/app" className={textLink}>
        {text.back}
      </Link>
    </div>
  );
}
