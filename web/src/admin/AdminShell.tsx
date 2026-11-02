import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, Outlet, useNavigate } from "@tanstack/react-router";

import { secondaryButton, textLink } from "../account/fields";
import { adminApi, fetchStaff } from "./api";
import { adminCopy as text } from "./copy";

async function logOut(): Promise<void> {
  const { response } = await adminApi.DELETE("/api/admin/session");
  if (!response.ok) {
    throw new Error(`Unexpected status ${String(response.status)}`);
  }
}

export function AdminShell() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const staff = useQuery({ queryKey: ["staff"], queryFn: fetchStaff });
  const leaving = useMutation({
    mutationFn: logOut,
    onSuccess: () => {
      queryClient.clear();
      void navigate({ to: "/ingresar" });
    },
  });

  if (staff.data === "login") {
    return <Navigate to="/ingresar" />;
  }
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6 text-base">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <nav aria-label={text.login.title} className="flex flex-wrap gap-5">
          <Link to="/" className={textLink}>
            {text.nav.accounts}
          </Link>
          <Link to="/cronograma" className={textLink}>
            {text.nav.schedule}
          </Link>
          <Link to="/reclamos" className={textLink}>
            {text.nav.complaints}
          </Link>
        </nav>
        <button
          type="button"
          className={secondaryButton}
          disabled={leaving.isPending}
          onClick={() => {
            leaving.mutate();
          }}
        >
          {text.nav.logout}
        </button>
      </header>
      {staff.isError && (
        <p role="alert" className="text-red-800">
          {text.failure}
        </p>
      )}
      {staff.data && (
        <main>
          <Outlet />
        </main>
      )}
    </div>
  );
}
