import {
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
} from "@tanstack/react-router";

import { LandingPage } from "./landing/LandingPage";

const rootRoute = createRootRoute({ component: Outlet });

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: LandingPage,
});

const privacyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/privacidad",
  component: lazyRouteComponent(() => import("./landing/PrivacyPage"), "PrivacyPage"),
});

export const routeTree = rootRoute.addChildren([landingRoute, privacyRoute]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
