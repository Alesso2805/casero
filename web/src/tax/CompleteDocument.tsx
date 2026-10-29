import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { primaryButton, SelectField, TextField } from "../account/fields";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { fetchRenters } from "../leases/LeasesPage";
import { taxCopy as text } from "./copy";

type Renter = components["schemas"]["RenterResponse"];

const DOC_TYPES = ["dni", "ce", "passport", "ruc"] as const;

const schema = z.object({
  docType: z.enum(DOC_TYPES),
  docNumber: z.string().trim().min(1, text.complete.required).max(30),
});

type DocumentValues = z.input<typeof schema>;

const REFUSALS: Record<string, string> = {
  invalid_document: text.complete.invalid,
  duplicate_document: text.complete.duplicate,
};

async function saveDocument(renter: Renter, values: DocumentValues): Promise<string | null> {
  const { data, error } = await api.PUT("/api/app/renters/{renter_id}", {
    params: { path: { renter_id: renter.id } },
    body: {
      full_name: renter.full_name,
      phone: renter.phone_e164,
      document: { doc_type: values.docType, number: values.docNumber.trim() },
    },
  });
  if (data) {
    return null;
  }
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return (typeof detail === "string" ? REFUSALS[detail] : undefined) ?? text.complete.failure;
}

export function CompleteDocument({ renterId, renterName }: { renterId: string; renterName: string }) {
  const queryClient = useQueryClient();
  const renters = useQuery({ queryKey: ["renters"], queryFn: fetchRenters });
  const renter =
    renters.data?.kind === "data" ? renters.data.data.find((r) => r.id === renterId) : undefined;
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<DocumentValues>({
    resolver: zodResolver(schema),
    defaultValues: { docType: "dni", docNumber: "" },
  });
  const save = useMutation({
    mutationFn: (values: DocumentValues) =>
      renter ? saveDocument(renter, values) : Promise.resolve(text.complete.failure),
    onSuccess: async (refusal) => {
      if (refusal) {
        setError("docNumber", { message: refusal });
        return;
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["renters"] }),
        queryClient.invalidateQueries({ queryKey: ["declarations"] }),
      ]);
    },
  });
  const id = `document-${renterId}`;
  return (
    <form
      noValidate
      aria-labelledby={`${id}-title`}
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        void handleSubmit((values) => {
          save.mutate(values);
        })(event);
      }}
    >
      <h4 id={`${id}-title`} className="font-semibold">
        {text.complete.title(renterName)}
      </h4>
      <SelectField
        id={`${id}-type`}
        label={text.complete.docType}
        error={errors.docType}
        registration={register("docType")}
      >
        {DOC_TYPES.map((type) => (
          <option key={type} value={type}>
            {text.docTypes[type]}
          </option>
        ))}
      </SelectField>
      <TextField
        id={`${id}-number`}
        label={text.complete.docNumber}
        autoComplete="off"
        error={errors.docNumber}
        registration={register("docNumber")}
      />
      <button
        type="submit"
        className={primaryButton}
        disabled={save.isPending || renters.isPending}
      >
        {save.isPending ? text.complete.saving : text.complete.save}
      </button>
      {save.isError && (
        <p role="alert" className="text-red-800">
          {text.complete.failure}
        </p>
      )}
    </form>
  );
}
