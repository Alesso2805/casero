import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { api } from "../api/client";
import { accountCopy as text } from "./copy";
import { secondaryButton } from "./fields";

export function useLogOut() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (everywhere: boolean) => {
      await (everywhere ? api.DELETE("/api/app/sessions") : api.DELETE("/api/app/session"));
    },
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: ["me"] });
      void navigate({ to: "/ingresar" });
    },
  });
}

export function LogOutButtons() {
  const logOut = useLogOut();
  return (
    <div className="flex flex-col gap-3 sm:flex-row">
      <button
        type="button"
        className={secondaryButton}
        disabled={logOut.isPending}
        onClick={() => {
          logOut.mutate(false);
        }}
      >
        {text.home.logOut}
      </button>
      <button
        type="button"
        className={secondaryButton}
        disabled={logOut.isPending}
        onClick={() => {
          logOut.mutate(true);
        }}
      >
        {text.home.logOutEverywhere}
      </button>
    </div>
  );
}
