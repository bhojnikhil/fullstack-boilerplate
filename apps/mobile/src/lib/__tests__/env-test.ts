import { readRuntimeEnv } from "../env";

describe("runtime env", () => {
  it("reads values app.config.ts put in extra", () => {
    expect(
      readRuntimeEnv({
        version: "1.0.0",
        extra: {
          apiUrl: "https://api.example.com",
          appVariant: "production",
          appDomain: "app.example.com",
          eas: {},
        },
      }),
    ).toEqual({
      apiUrl: "https://api.example.com",
      appVariant: "production",
      appVersion: "1.0.0",
      appDomain: "app.example.com",
      sentryDsn: undefined,
    });
  });

  it.each([
    null,
    { version: "1.0.0", extra: {} },
    { version: "1.0.0", extra: { apiUrl: "http://x", appVariant: "staging" } },
    { extra: { apiUrl: "http://x", appVariant: "development" } },
  ])("throws when config is missing or invalid: %o", (config) => {
    expect(() => readRuntimeEnv(config)).toThrow(/app\.config\.ts/);
  });
});
