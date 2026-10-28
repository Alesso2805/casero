import {
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
  useMatches,
} from "@tanstack/react-router";
import { useEffect } from "react";

import { ErrorPage, NotFoundPage } from "./errors";
import { LandingPage } from "./landing/LandingPage";

function Root() {
  const title = useMatches({ select: (matches) => matches.at(-1)?.staticData.title });
  useEffect(() => {
    document.title = title ? `${title} · Casero` : "Casero";
  }, [title]);
  return <Outlet />;
}

const rootRoute = createRootRoute({ component: Root });

const landingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: LandingPage,
});

const privacyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/privacidad",
  staticData: { title: "Política de privacidad" },
  component: lazyRouteComponent(() => import("./landing/PrivacyPage"), "PrivacyPage"),
});

const complaintsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/libro-de-reclamaciones",
  staticData: { title: "Libro de Reclamaciones" },
  component: lazyRouteComponent(
    () => import("./landing/complaints/ComplaintsPage"),
    "ComplaintsPage",
  ),
});

const unsubscribeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/baja",
  staticData: { title: "Dejar de recibir correos" },
  component: lazyRouteComponent(() => import("./landing/UnsubscribePage"), "UnsubscribePage"),
});

const calculatorRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/calculadora",
  staticData: { title: "¿Cuánto pago a SUNAT por mi alquiler?" },
  component: lazyRouteComponent(
    () => import("./landing/calculator/CalculatorPage"),
    "CalculatorPage",
  ),
});

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/registro",
  staticData: { title: "Crea tu cuenta" },
  component: lazyRouteComponent(() => import("./account/RegisterPage"), "RegisterPage"),
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/ingresar",
  staticData: { title: "Ingresar" },
  component: lazyRouteComponent(() => import("./account/LoginPage"), "LoginPage"),
});

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app",
  staticData: { title: "Inicio" },
  component: lazyRouteComponent(() => import("./account/AppHome"), "AppHome"),
});

const profileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/mis-datos",
  staticData: { title: "Mis datos" },
  component: lazyRouteComponent(() => import("./account/ProfilePage"), "ProfilePage"),
});

const propertiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/inmuebles",
  staticData: { title: "Mis inmuebles" },
  component: lazyRouteComponent(() => import("./properties/PropertiesPage"), "PropertiesPage"),
});

const newPropertyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/inmuebles/nuevo",
  staticData: { title: "Nuevo inmueble" },
  component: lazyRouteComponent(() => import("./properties/NewPropertyPage"), "NewPropertyPage"),
});

const propertyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/inmuebles/$propertyId",
  staticData: { title: "Editar inmueble" },
  component: lazyRouteComponent(() => import("./properties/EditPropertyPage"), "EditPropertyPage"),
});

const leasesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/contratos",
  staticData: { title: "Mis contratos" },
  component: lazyRouteComponent(() => import("./leases/LeasesPage"), "LeasesPage"),
});

const newLeaseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/contratos/nuevo",
  staticData: { title: "Nuevo contrato" },
  component: lazyRouteComponent(() => import("./leases/NewLeasePage"), "NewLeasePage"),
});

const leaseRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/app/contratos/$leaseId",
  staticData: { title: "Cobros del contrato" },
  component: lazyRouteComponent(() => import("./leases/LeasePage"), "LeasePage"),
});

const verifyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/verificar",
  staticData: { title: "Confirmar tu correo" },
  component: lazyRouteComponent(() => import("./account/VerifyPage"), "VerifyPage"),
});

const forgotRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/recuperar",
  staticData: { title: "Recupera tu contraseña" },
  component: lazyRouteComponent(() => import("./account/ForgotPasswordPage"), "ForgotPasswordPage"),
});

const newPasswordRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/nueva-clave",
  staticData: { title: "Elige tu nueva contraseña" },
  component: lazyRouteComponent(() => import("./account/NewPasswordPage"), "NewPasswordPage"),
});

const legalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/legal/$document",
  staticData: { title: "Documentos legales" },
  component: lazyRouteComponent(() => import("./landing/LegalDocumentPage"), "LegalDocumentPage"),
});

const legalVersionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/legal/$document/$version",
  staticData: { title: "Documentos legales" },
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
  interface StaticDataRouteOption {
    title?: string;
  }
}
