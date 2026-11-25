import type { ErrorEvent } from "@sentry/react-native";

import { initSentry, scrubEvent } from "../sentry";

const base = { appVariant: "production", appVersion: "1.4.0" } as const;

describe("initSentry", () => {
  it("does nothing without a DSN", () => {
    const init = jest.fn();
    expect(initSentry({ ...base, sentryDsn: undefined }, init)).toBe(false);
    expect(init).not.toHaveBeenCalled();
  });

  it("starts Sentry with release, environment and no personal data", () => {
    const init = jest.fn();
    expect(
      initSentry({ ...base, sentryDsn: "https://k@o0.ingest.sentry.io/1" }, init),
    ).toBe(true);
    expect(init).toHaveBeenCalledTimes(1);
    expect(init).toHaveBeenCalledWith(
      expect.objectContaining({
        dsn: "https://k@o0.ingest.sentry.io/1",
        environment: "production",
        release: "mobile@1.4.0",
        sendDefaultPii: false,
        tracesSampleRate: 0,
        maxBreadcrumbs: 0,
        attachScreenshot: false,
        attachViewHierarchy: false,
        beforeSend: scrubEvent,
      }),
    );
  });
});

describe("scrubEvent", () => {
  it("drops user, request, breadcrumbs and extra data but keeps the error", () => {
    const event = {
      user: { email: "person@example.com" },
      request: { url: "https://app/verify#token=secret" },
      breadcrumbs: [{ message: "tapped" }],
      extra: { note: "x" },
      exception: { values: [{ type: "TypeError", value: "boom" }] },
      release: "mobile@1.4.0",
    } as unknown as ErrorEvent;
    expect(scrubEvent(event)).toEqual({
      exception: { values: [{ type: "TypeError", value: "boom" }] },
      release: "mobile@1.4.0",
    });
  });
});
