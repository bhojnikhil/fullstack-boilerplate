import type { ConfigContext } from "expo/config";

import appConfig, { parseAppEnv } from "../app.config";

const ctx = { config: {} } as ConfigContext;

describe("parseAppEnv", () => {
  it("defaults to a development build against a local API", () => {
    const env = parseAppEnv({});
    expect(env).toMatchObject({
      variant: "development",
      name: "Boilerplate (Dev)",
      scheme: "boilerplate-dev",
      androidPackage: "com.example.boilerplate.dev",
      iosBundleId: "com.example.boilerplate.dev",
      apiUrl: "http://localhost:8000",
      appDomain: undefined,
      sentryDsn: undefined,
    });
  });

  it("uses unsuffixed ids for production and strips trailing slashes", () => {
    const env = parseAppEnv({
      APP_VARIANT: "production",
      API_URL: "https://api.example.com/",
      ANDROID_PACKAGE: "com.acme.app",
      IOS_BUNDLE_ID: "com.acme.ios",
      APP_SCHEME: "acme",
    });
    expect(env).toMatchObject({
      name: "Boilerplate",
      scheme: "acme",
      androidPackage: "com.acme.app",
      iosBundleId: "com.acme.ios",
      apiUrl: "https://api.example.com",
    });
  });

  it("suffixes preview ids", () => {
    const env = parseAppEnv({
      APP_VARIANT: "preview",
      API_URL: "https://api.example.com",
    });
    expect(env.androidPackage).toBe("com.example.boilerplate.preview");
    expect(env.scheme).toBe("boilerplate-preview");
  });

  it.each([
    [{ APP_VARIANT: "staging" }, /APP_VARIANT/],
    [{ APP_VARIANT: "preview" }, /API_URL is required/],
    [{ APP_VARIANT: "production", API_URL: "http://api.example.com" }, /https:\/\//],
    [{ API_URL: "localhost:8000" }, /absolute http\(s\) URL/],
    [{ ANDROID_PACKAGE: "app" }, /ANDROID_PACKAGE/],
    [{ APP_SCHEME: "My App" }, /APP_SCHEME/],
    [{ APP_DOMAIN: "https://app.example.com" }, /APP_DOMAIN/],
    [{ EAS_PROJECT_ID: "not-a-uuid" }, /EAS_PROJECT_ID/],
  ])("rejects %o", (env, message) => {
    expect(() => parseAppEnv(env)).toThrow(message);
  });
});

describe("app.config.ts", () => {
  const saved = { ...process.env };
  afterEach(() => {
    process.env = { ...saved };
  });

  it("adds no app links or update URL when the domain and project are unset", () => {
    delete process.env.APP_DOMAIN;
    delete process.env.EAS_PROJECT_ID;
    const config = appConfig(ctx);
    expect(config.android?.intentFilters).toBeUndefined();
    expect(config.ios?.associatedDomains).toBeUndefined();
    expect(config.updates).toBeUndefined();
  });

  it("derives App Links, associated domains and the update URL from env", () => {
    process.env.APP_DOMAIN = "app.example.com";
    process.env.EAS_PROJECT_ID = "123e4567-e89b-12d3-a456-426614174000";
    process.env.SENTRY_DSN = "https://key@o0.ingest.sentry.io/0";
    const config = appConfig(ctx);
    expect(config.ios?.associatedDomains).toEqual(["applinks:app.example.com"]);
    const [filter] = config.android?.intentFilters ?? [];
    expect(filter).toMatchObject({ action: "VIEW", autoVerify: true });
    expect(filter?.data).toContainEqual({
      scheme: "https",
      host: "app.example.com",
      pathPrefix: "/invite",
    });
    expect(config.updates?.url).toBe(
      "https://u.expo.dev/123e4567-e89b-12d3-a456-426614174000",
    );
    expect(config.extra).toMatchObject({
      appDomain: "app.example.com",
      sentryDsn: "https://key@o0.ingest.sentry.io/0",
      eas: { projectId: "123e4567-e89b-12d3-a456-426614174000" },
    });
    expect(config.runtimeVersion).toEqual({ policy: "appVersion" });
  });
});
