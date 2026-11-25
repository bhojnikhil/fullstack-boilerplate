import { createAppServices, type AppServices } from "../src/lib/app-services";

import {
  apiError,
  createFakeFetch,
  json,
  makeAccessToken,
  memoryTokenStorage,
  tokenResponse,
} from "./fake-api";

export const SIGNED_IN_TOKENS = {
  accessToken: makeAccessToken("sid-1", "user-1"),
  refreshToken: "refresh-1",
};

export const PROFILE = tokenResponse("sid-1").user;

export type Handlers = Parameters<typeof createFakeFetch>[0];

/** The API as a signed-in user with no data; tests override what they need. */
export function defaultHandlers(): Handlers {
  return {
    "GET /v1/me": () => json(200, PROFILE),
    "GET /v1/items": () => json(200, { items: [], next_cursor: null }),
    "GET /v1/workspaces": () => json(200, { items: [] }),
    "POST /v1/auth/logout": () => json(204, null),
  };
}

export function makeServices(
  handlers: Handlers = defaultHandlers(),
  tokens: typeof SIGNED_IN_TOKENS | null = SIGNED_IN_TOKENS,
): { services: AppServices } & ReturnType<typeof createFakeFetch> & {
    storage: ReturnType<typeof memoryTokenStorage>;
  } {
  const fake = createFakeFetch(handlers);
  const storage = memoryTokenStorage(tokens);
  const services = createAppServices({
    baseUrl: "https://api.test",
    headers: { "X-App-Version": "1.0.0", "X-Platform": "android" },
    storage,
    fetch: fake.fetch,
  });
  return { services, storage, ...fake };
}

export { apiError, json, tokenResponse };
