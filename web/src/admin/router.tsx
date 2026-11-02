import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";

import { AccountPage } from "./AccountPage";
import { AccountsPage } from "./AccountsPage";
import { AdminLogin } from "./AdminLogin";
import { AdminShell } from "./AdminShell";
import { ComplaintsPage } from "./ComplaintsPage";
import { SchedulePage } from "./SchedulePage";

const rootRoute = createRootRoute();

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/ingresar",
  component: AdminLogin,
});

const shellRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "shell",
  component: AdminShell,
});

const accountsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/",
  component: AccountsPage,
});

const accountRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/cuentas/$accountId",
  component: AccountPage,
});

const scheduleRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/cronograma",
  component: SchedulePage,
});

const complaintsRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/reclamos",
  component: ComplaintsPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  shellRoute.addChildren([accountsRoute, accountRoute, scheduleRoute, complaintsRoute]),
]);

export function createAdminRouter(history?: RouterHistory) {
  return createRouter({ routeTree, basepath: "/admin", history });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAdminRouter>;
  }
}
