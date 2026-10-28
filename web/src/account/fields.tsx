import { type ReactNode, useState } from "react";
import type { FieldError, UseFormRegisterReturn } from "react-hook-form";

import { accountCopy as text } from "./copy";

const inputClass = "min-h-11 w-full rounded-lg border border-stone-400 px-3 text-base";

export const primaryButton =
  "min-h-11 rounded-lg bg-brand px-5 text-base font-semibold text-white hover:bg-brand-dark disabled:opacity-60";
export const secondaryButton =
  "min-h-11 rounded-lg border border-brand px-5 text-base font-semibold text-brand disabled:opacity-60";

function describedBy(id: string, hint: boolean, error: boolean): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

export function ErrorText({ id, error }: { id: string; error: FieldError | undefined }) {
  return error ? (
    <p id={`${id}-error`} className="text-base text-red-800">
      {error.message}
    </p>
  ) : null;
}

export function TextField({
  id,
  label,
  type = "text",
  numeric = false,
  decimal = false,
  autoComplete,
  hint,
  error,
  registration,
}: {
  id: string;
  label: string;
  type?: "text" | "email" | "date";
  numeric?: boolean;
  decimal?: boolean;
  autoComplete?: string;
  hint?: string;
  error: FieldError | undefined;
  registration: UseFormRegisterReturn;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-base font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-base text-stone-600">
          {hint}
        </p>
      )}
      <input
        id={id}
        type={type}
        inputMode={type === "email" ? "email" : decimal ? "decimal" : numeric ? "numeric" : undefined}
        autoComplete={autoComplete}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, Boolean(hint), Boolean(error))}
        className={inputClass}
        {...registration}
      />
      <ErrorText id={id} error={error} />
    </div>
  );
}

export function PasswordField({
  id,
  autoComplete,
  hint,
  error,
  registration,
}: {
  id: string;
  autoComplete: "current-password" | "new-password";
  hint?: string;
  error: FieldError | undefined;
  registration: UseFormRegisterReturn;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-base font-medium">
        {text.fields.password}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-base text-stone-600">
          {hint}
        </p>
      )}
      <div className="flex gap-2">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, Boolean(hint), Boolean(error))}
          className={inputClass}
          {...registration}
        />
        <button
          type="button"
          className="min-h-11 shrink-0 rounded-lg border border-stone-400 px-3"
          aria-controls={id}
          onClick={() => {
            setVisible(!visible);
          }}
        >
          {visible ? text.fields.hide : text.fields.show}
        </button>
      </div>
      <ErrorText id={id} error={error} />
    </div>
  );
}

export function SelectField({
  id,
  label,
  hint,
  error,
  registration,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  error: FieldError | undefined;
  registration: UseFormRegisterReturn;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-base font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="text-base text-stone-600">
          {hint}
        </p>
      )}
      <select
        id={id}
        className="min-h-11 w-full rounded-lg border border-stone-400 bg-white px-3 text-base"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, Boolean(hint), Boolean(error))}
        {...registration}
      >
        {children}
      </select>
      <ErrorText id={id} error={error} />
    </div>
  );
}
