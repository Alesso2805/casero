import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";

import { AccountsPage } from "./AccountsPage";
import { AdminLogin } from "./AdminLogin";
import { AdminShell } from "./AdminShell";

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

const routeTree = rootRoute.addChildren([loginRoute, shellRoute.addChildren([accountsRoute])]);

export function createAdminRouter(history?: RouterHistory) {
  return createRouter({ routeTree, basepath: "/admin", history });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAdminRouter>;
  }
}
