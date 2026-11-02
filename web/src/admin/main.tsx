import "../styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { configureValidation } from "../validation";
import { createAdminRouter } from "./router";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Missing #root element");
}

configureValidation();

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <RouterProvider router={createAdminRouter()} />
    </QueryClientProvider>
  </StrictMode>,
);
