import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { listenForErrors } from "./errors";
import { router } from "./router";
import { configureValidation } from "./validation";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Missing #root element");
}

if (import.meta.env.PROD) {
  listenForErrors();
}

configureValidation();

const queryClient = new QueryClient();

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
