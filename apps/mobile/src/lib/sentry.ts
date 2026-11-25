import * as Sentry from "@sentry/react-native";
import type { ErrorEvent } from "@sentry/react-native";

import type { RuntimeEnv } from "./env";

type SentryInit = typeof Sentry.init;

/**
 * Removes anything that could identify the person from an event: the user,
 * request details (URLs can carry tokens) and breadcrumbs. Exception types,
 * messages and stack frames stay.
 */
export function scrubEvent(event: ErrorEvent): ErrorEvent {
  delete event.user;
  delete event.request;
  delete event.breadcrumbs;
  delete event.extra;
  return event;
}

/**
 * Starts Sentry when `SENTRY_DSN` was configured at build time; does nothing
 * (and returns false) otherwise, so builds without a DSN never contact Sentry.
 * No personal data is sent by default: see `scrubEvent` and `sendDefaultPii`.
 */
export function initSentry(
  env: Pick<RuntimeEnv, "sentryDsn" | "appVariant" | "appVersion">,
  init: SentryInit = Sentry.init,
): boolean {
  if (!env.sentryDsn) return false;
  init({
    dsn: env.sentryDsn,
    environment: env.appVariant,
    release: `mobile@${env.appVersion}`,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    maxBreadcrumbs: 0,
    attachScreenshot: false,
    attachViewHierarchy: false,
    beforeSend: scrubEvent,
  });
  return true;
}
