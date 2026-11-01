import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, waitFor } from "@testing-library/react";

import { ErrorPage, NotFoundPage } from "../errors";
import { routeTree } from "../router";

export async function renderPage(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    defaultErrorComponent: ErrorPage,
    defaultNotFoundComponent: NotFoundPage,
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await router.load();
  // An absence is only proof once the data that could have shown the element has arrived.
  const settled = async () => {
    await waitFor(() => {
      if (queryClient.isFetching() > 0) {
        throw new Error("Queries still running");
      }
    });
    await act(() => new Promise((resolve) => setTimeout(resolve)));
  };
  return { ...result, settled };
}
