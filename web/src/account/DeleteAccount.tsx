import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { api } from "../api/client";
import { ConfirmButton } from "./ConfirmButton";
import { accountCopy as text } from "./copy";

async function requestDeletion(): Promise<string> {
  const { data } = await api.POST("/api/app/account/deletion");
  if (!data) {
    throw new Error("Deletion not requested");
  }
  return data.purge_on;
}

/** With the download beside it: SPEC asks to offer the export before deleting. */
export function DeleteAccount() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const remove = useMutation({
    mutationFn: requestDeletion,
    onSuccess: async (purgeOn) => {
      queryClient.clear();
      await navigate({ to: "/cuenta-eliminada/$purgeOn", params: { purgeOn } });
    },
  });
  return (
    <section aria-labelledby="delete-account-title" className="flex flex-col gap-3">
      <h2 id="delete-account-title" className="text-2xl font-bold">
        {text.deletion.title}
      </h2>
      <p>{text.deletion.intro}</p>
      <p>{text.deletion.sunat}</p>
      <ConfirmButton
        id="delete-account"
        label={text.deletion.button}
        question={text.deletion.question}
        confirmLabel={text.deletion.confirm}
        cancelLabel={text.deletion.cancel}
        busy={remove.isPending}
        onConfirm={() => {
          remove.mutate();
        }}
      />
      {remove.isError && (
        <p role="alert" className="text-red-800">
          {text.deletion.failure}
        </p>
      )}
    </section>
  );
}
