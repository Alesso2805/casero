import {
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
} from "@tanstack/react-router";

import { ErrorPage, NotFoundPage } from "./errors";
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

const complaintsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/libro-de-reclamaciones",
  component: lazyRouteComponent(
    () => import("./landing/complaints/ComplaintsPage"),
    "ComplaintsPage",
  ),
});

const unsubscribeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/baja",
  component: lazyRouteComponent(() => import("./landing/UnsubscribePage"), "UnsubscribePage"),
});

const calculatorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/calculadora",
  component: lazyRouteComponent(
    () => import("./landing/calculator/CalculatorPage"),
    "CalculatorPage",
  ),
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/registro",
  component: lazyRouteComponent(() => import("./account/RegisterPage"), "RegisterPage"),
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/ingresar",
  component: lazyRouteComponent(() => import("./account/LoginPage"), "LoginPage"),
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app",
  component: lazyRouteComponent(() => import("./account/AppHome"), "AppHome"),
});

const profileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/mis-datos",
  component: lazyRouteComponent(() => import("./account/ProfilePage"), "ProfilePage"),
});

const propertiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/inmuebles",
  component: lazyRouteComponent(() => import("./properties/PropertiesPage"), "PropertiesPage"),
});

const newPropertyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/inmuebles/nuevo",
  component: lazyRouteComponent(() => import("./properties/NewPropertyPage"), "NewPropertyPage"),
});

const propertyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/inmuebles/$propertyId",
  component: lazyRouteComponent(() => import("./properties/EditPropertyPage"), "EditPropertyPage"),
});

const leasesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/contratos",
  component: lazyRouteComponent(() => import("./leases/LeasesPage"), "LeasesPage"),
});

const newLeaseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/contratos/nuevo",
  component: lazyRouteComponent(() => import("./leases/NewLeasePage"), "NewLeasePage"),
});

const leaseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/contratos/$leaseId",
  component: lazyRouteComponent(() => import("./leases/LeasePage"), "LeasePage"),
});

const verifyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/verificar",
  component: lazyRouteComponent(() => import("./account/VerifyPage"), "VerifyPage"),
});

const forgotRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/recuperar",
  component: lazyRouteComponent(() => import("./account/ForgotPasswordPage"), "ForgotPasswordPage"),
});

const newPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/nueva-clave",
  component: lazyRouteComponent(() => import("./account/NewPasswordPage"), "NewPasswordPage"),
});

const legalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/legal/$document",
  component: lazyRouteComponent(() => import("./landing/LegalDocumentPage"), "LegalDocumentPage"),
});

const legalVersionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/legal/$document/$version",
  component: lazyRouteComponent(() => import("./landing/LegalDocumentPage"), "LegalDocumentPage"),
});

export const routeTree = rootRoute.addChildren([
  landingRoute,
  privacyRoute,
  complaintsRoute,
  unsubscribeRoute,
  calculatorRoute,
  registerRoute,
  loginRoute,
  appRoute,
  profileRoute,
  propertiesRoute,
  newPropertyRoute,
  propertyRoute,
  leasesRoute,
  newLeaseRoute,
  leaseRoute,
  verifyRoute,
  forgotRoute,
  newPasswordRoute,
  legalRoute,
  legalVersionRoute,
]);

export const router = createRouter({
  routeTree,
  defaultErrorComponent: ErrorPage,
  defaultNotFoundComponent: NotFoundPage,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
