import createClient from "openapi-fetch";

import { csrfMiddleware } from "./csrf";
import type { paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  fetch: (request) => globalThis.fetch(request),
});

api.use(csrfMiddleware("/api/public/csrf"));
