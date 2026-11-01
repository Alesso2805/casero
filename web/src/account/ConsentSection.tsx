import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { api } from "../api/client";
import { ConfirmButton } from "./ConfirmButton";
import { accountCopy as text } from "./copy";

async function withdrawConsent(): Promise<void> {
  const { data } = await api.POST("/api/app/legal/consent-withdrawal");
  if (!data) {
    throw new Error("Consent not withdrawn");
  }
}

export function ConsentSection() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const withdraw = useMutation({
    mutationFn: withdrawConsent,
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      await navigate({ to: "/app" });
    },
  });
  return (
    <section aria-labelledby="consent-title" className="flex flex-col gap-3">
      <h2 id="consent-title" className="text-2xl font-bold">
        {text.profile.consentTitle}
      </h2>
      <p>{text.profile.consentIntro}</p>
      <ConfirmButton
        id="consent-withdrawal"
        label={text.profile.withdraw}
        question={text.profile.withdrawQuestion}
        confirmLabel={text.profile.withdrawConfirm}
        cancelLabel={text.profile.withdrawCancel}
        busy={withdraw.isPending}
        onConfirm={() => {
          withdraw.mutate();
        }}
      />
      {withdraw.isError && (
        <p role="alert" className="text-red-800">
          {text.errors.failure}
        </p>
      )}
    </section>
  );
}
