import type { ConfigContext } from "expo/config";

import appConfig, {
  APP_CONFIG_ENV_KEYS,
  APP_VERSION,
  BLOCKED_ANDROID_PERMISSIONS,
  googleIosUrlScheme,
  isEasContext,
  parseAppEnv,
  runtimeVersionFor,
  withoutAppConfigEnv,
} from "../app.config";

const ctx = { config: {} } as ConfigContext;

/** A valid production environment; tests override single values. */
const PRODUCTION = {
  APP_VARIANT: "production",
  API_URL: "https://api.acme.dev",
  ANDROID_PACKAGE: "dev.acme.app",
  IOS_BUNDLE_ID: "dev.acme.app",
};

const SENTINEL = "s3cr3t-SENTINEL";

describe("parseAppEnv", () => {
  it("defaults to a development build against a local API", () => {
    expect(parseAppEnv({})).toMatchObject({
      variant: "development",
      name: "Boilerplate (Dev)",
      scheme: "boilerplate-dev",
      androidPackage: "com.example.boilerplate.dev",
      iosBundleId: "com.example.boilerplate.dev",
      apiUrl: "http://localhost:8000",
      appDomain: undefined,
      appLinkPaths: [],
      sentryDsn: undefined,
    });
  });

  it("reads public Google client ids and adds the iOS URL scheme plugin only with the iOS id", () => {
    const WEB = "123-web.apps.googleusercontent.com";
    const IOS = "456-ios.apps.googleusercontent.com";
    const env = parseAppEnv({ GOOGLE_WEB_CLIENT_ID: WEB, GOOGLE_IOS_CLIENT_ID: IOS });
    expect(env).toMatchObject({ googleWebClientId: WEB, googleIosClientId: IOS });
    expect(googleIosUrlScheme(IOS)).toBe("com.googleusercontent.apps.456-ios");
    expect(() => parseAppEnv({ GOOGLE_WEB_CLIENT_ID: "not-a-client-id" })).toThrow(
      /GOOGLE_WEB_CLIENT_ID/,
    );
    const pluginNames = (vars: Record<string, string>) => {
      Object.assign(process.env, vars);
      try {
        return (appConfig(ctx).plugins ?? []).map((p) => (Array.isArray(p) ? p[0] : p));
      } finally {
        for (const key of Object.keys(vars)) delete process.env[key];
      }
    };
    expect(pluginNames({})).not.toContain("@react-native-google-signin/google-signin");
    expect(pluginNames({ GOOGLE_IOS_CLIENT_ID: IOS })).toContain(
      "@react-native-google-signin/google-signin",
    );
  });

  it("uses unsuffixed ids for production and normalizes the API URL", () => {
    const env = parseAppEnv({
      ...PRODUCTION,
      API_URL: "https://API.acme.dev/base/",
      APP_SCHEME: "acme",
    });
    expect(env).toMatchObject({
      name: "Boilerplate",
      scheme: "acme",
      androidPackage: "dev.acme.app",
      iosBundleId: "dev.acme.app",
      apiUrl: "https://api.acme.dev/base",
    });
  });

  it("suffixes preview ids and keeps the com.example default outside production", () => {
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
    [{ ...PRODUCTION, API_URL: undefined }, /API_URL is required/],
    [{ ...PRODUCTION, API_URL: "http://api.acme.dev" }, /https:\/\//],
    [{ API_URL: "localhost:8000" }, /absolute http\(s\) URL/],
    [{ ANDROID_PACKAGE: "app" }, /ANDROID_PACKAGE/],
    [{ APP_SCHEME: "My App" }, /APP_SCHEME/],
    [{ APP_DOMAIN: "https://app.example.com" }, /APP_DOMAIN/],
    [{ EAS_PROJECT_ID: "not-a-uuid" }, /EAS_PROJECT_ID/],
  ])("rejects %o", (env, message) => {
    expect(() => parseAppEnv(env)).toThrow(message);
  });
});

describe("APP_VARIANT under EAS (M1)", () => {
  it("detects EAS CLI and EAS Build workers", () => {
    expect(isEasContext({})).toBe(false);
    expect(isEasContext({ EXPO_NO_DOTENV: "1" })).toBe(true);
    expect(isEasContext({ EAS_BUILD: "true" })).toBe(true);
    expect(isEasContext({ EXPO_NO_DOTENV: "0" })).toBe(false);
  });

  it.each([{ EXPO_NO_DOTENV: "1" }, { EAS_BUILD: "true" }])(
    "fails closed instead of defaulting to development: %o",
    (env) => {
      expect(() => parseAppEnv(env)).toThrow(/APP_VARIANT is required/);
    },
  );

  it("accepts an explicit variant under EAS", () => {
    expect(parseAppEnv({ ...PRODUCTION, EXPO_NO_DOTENV: "1" }).variant).toBe(
      "production",
    );
  });

  it.each([
    ["preview", "production"],
    ["development", "preview"],
  ])("rejects APP_VARIANT=%s in EAS build profile %s", (variant, profile) => {
    expect(() =>
      parseAppEnv({
        ...PRODUCTION,
        APP_VARIANT: variant,
        EAS_BUILD: "true",
        EAS_BUILD_PROFILE: profile,
      }),
    ).toThrow(/does not match the EAS build profile/);
  });

  it("allows custom profile names", () => {
    expect(
      parseAppEnv({
        ...PRODUCTION,
        EAS_BUILD: "true",
        EAS_BUILD_PROFILE: "production-apk",
      }).variant,
    ).toBe("production");
  });

  it("never falls back to localhost outside development", () => {
    for (const variant of ["preview", "production"]) {
      expect(() =>
        parseAppEnv({ ...PRODUCTION, APP_VARIANT: variant, API_URL: undefined }),
      ).toThrow(/API_URL is required/);
    }
  });

  it("gives every variant its own runtime version", () => {
    const runtimes = new Set(
      (["development", "preview", "production"] as const).map(runtimeVersionFor),
    );
    expect(runtimes.size).toBe(3);
    expect(runtimeVersionFor("preview")).toBe(`${APP_VERSION}-preview`);
  });
});

describe("API_URL hygiene (M4)", () => {
  it.each([
    [`https://user:${SENTINEL}@api.acme.dev`, /without credentials/],
    [`https://${SENTINEL}@api.acme.dev`, /without credentials/],
    [`https://api.acme.dev/?token=${SENTINEL}`, /query string or fragment/],
    [`https://api.acme.dev/#${SENTINEL}`, /query string or fragment/],
    [`https://api.acme.dev/?`, /query string or fragment/],
    [`ftp://${SENTINEL}.example`, /absolute http\(s\) URL/],
    [`not a url ${SENTINEL}`, /absolute http\(s\) URL/],
  ])("rejects %s without echoing it", (apiUrl, message) => {
    let error: unknown;
    try {
      parseAppEnv({ ...PRODUCTION, API_URL: apiUrl });
    } catch (e) {
      error = e;
    }
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toMatch(message);
    expect((error as Error).message).not.toContain(SENTINEL);
    expect(String((error as Error).stack)).not.toContain(SENTINEL);
  });

  it("does not echo other invalid values", () => {
    for (const key of [
      "APP_VARIANT",
      "ANDROID_PACKAGE",
      "APP_DOMAIN",
      "EAS_PROJECT_ID",
    ]) {
      expect(() => parseAppEnv({ [key]: `${SENTINEL} x` })).toThrow(
        expect.objectContaining({ message: expect.not.stringContaining(SENTINEL) }),
      );
    }
  });
});

describe("app ids (M8, m2)", () => {
  it.each([
    [{ ANDROID_PACKAGE: undefined }, "ANDROID_PACKAGE"],
    [{ IOS_BUNDLE_ID: undefined }, "IOS_BUNDLE_ID"],
    [{ ANDROID_PACKAGE: "com.example.myapp" }, "ANDROID_PACKAGE"],
    [{ IOS_BUNDLE_ID: "com.example" }, "IOS_BUNDLE_ID"],
  ])("production requires a real id: %o", (override, key) => {
    expect(() => parseAppEnv({ ...PRODUCTION, ...override })).toThrow(
      new RegExp(`${key} is required for production`),
    );
  });

  it("accepts underscores only in the Android package", () => {
    expect(parseAppEnv({ ANDROID_PACKAGE: "com.example.my_app" }).androidPackage).toBe(
      "com.example.my_app.dev",
    );
    expect(() => parseAppEnv({ IOS_BUNDLE_ID: "com.example.my_app" })).toThrow(
      /Invalid IOS_BUNDLE_ID/,
    );
  });

  it("accepts hyphens only in the iOS bundle id", () => {
    expect(parseAppEnv({ IOS_BUNDLE_ID: "com.example.my-app" }).iosBundleId).toBe(
      "com.example.my-app.dev",
    );
    expect(() => parseAppEnv({ ANDROID_PACKAGE: "com.example.my-app" })).toThrow(
      /Invalid ANDROID_PACKAGE/,
    );
  });
});

describe("APP_LINK_PATHS (M9)", () => {
  const domain = { APP_DOMAIN: "app.acme.dev" };

  it("parses exact paths and segment-bounded prefixes", () => {
    expect(
      parseAppEnv({
        ...domain,
        APP_LINK_PATHS: "/verify-email, /invite/ ,/verify-email",
      }).appLinkPaths,
    ).toEqual([
      { kind: "exact", path: "/verify-email" },
      { kind: "prefix", path: "/invite/" },
    ]);
  });

  it("needs APP_DOMAIN", () => {
    expect(() => parseAppEnv({ APP_LINK_PATHS: "/invite/" })).toThrow(
      /needs APP_DOMAIN/,
    );
  });

  it.each(["/", "//", "/invite/*", "invite", "/a b", "/.*"])("rejects %p", (path) => {
    expect(() => parseAppEnv({ ...domain, APP_LINK_PATHS: path })).toThrow(
      /Invalid APP_LINK_PATHS/,
    );
  });

  it.each([
    "/privacy",
    "/terms",
    "/account-deletion",
    "/account-deletion/",
    "/account-deletion/request",
    "/.well-known/",
    "/.well-known/assetlinks.json",
  ])("never claims web-only page %p", (path) => {
    expect(() => parseAppEnv({ ...domain, APP_LINK_PATHS: path })).toThrow(
      /must not claim/,
    );
  });

  it("allows paths that only share a prefix with web-only pages", () => {
    expect(
      parseAppEnv({ ...domain, APP_LINK_PATHS: "/terms-of-play" }).appLinkPaths,
    ).toEqual([{ kind: "exact", path: "/terms-of-play" }]);
  });
});

describe("app.config.ts", () => {
  const saved = { ...process.env };
  afterEach(() => {
    process.env = { ...saved };
  });

  /** Evaluates app.config.ts with exactly `env` as its app settings (R2-7). */
  function withEnv(env: Record<string, string>) {
    process.env = { ...withoutAppConfigEnv(saved), ...env };
    return appConfig(ctx);
  }

  it("adds no app links or update URL by default", () => {
    const config = withEnv({});
    expect(config.android?.intentFilters).toBeUndefined();
    expect(config.ios?.associatedDomains).toBeUndefined();
    expect(config.updates).toBeUndefined();
  });

  it("adds no app links for a domain without an explicit path list", () => {
    const config = withEnv({ APP_DOMAIN: "app.acme.dev" });
    expect(config.android?.intentFilters).toBeUndefined();
    expect(config.ios?.associatedDomains).toBeUndefined();
  });

  it("derives App Links, associated domains and the update URL from env", () => {
    const config = withEnv({
      APP_DOMAIN: "app.acme.dev",
      APP_LINK_PATHS: "/verify-email,/invite/",
      EAS_PROJECT_ID: "123e4567-e89b-12d3-a456-426614174000",
      SENTRY_DSN: "https://key@o0.ingest.sentry.io/0",
    });
    expect(config.ios?.associatedDomains).toEqual(["applinks:app.acme.dev"]);
    expect(config.android?.intentFilters).toEqual([
      {
        action: "VIEW",
        autoVerify: true,
        data: [
          { scheme: "https", host: "app.acme.dev", path: "/verify-email" },
          { scheme: "https", host: "app.acme.dev", pathPrefix: "/invite/" },
        ],
        category: ["BROWSABLE", "DEFAULT"],
      },
    ]);
    expect(config.updates?.url).toBe(
      "https://u.expo.dev/123e4567-e89b-12d3-a456-426614174000",
    );
    expect(config.extra).toMatchObject({
      appDomain: "app.acme.dev",
      sentryDsn: "https://key@o0.ingest.sentry.io/0",
      eas: { projectId: "123e4567-e89b-12d3-a456-426614174000" },
    });
  });

  it("uses the variant-specific runtime version", () => {
    expect(withEnv({}).runtimeVersion).toBe(`${APP_VERSION}-development`);
    expect(withEnv(PRODUCTION).runtimeVersion).toBe(`${APP_VERSION}-production`);
  });

  it("turns off Android backup and blocks unused permissions", () => {
    const config = withEnv({});
    expect(config.android?.allowBackup).toBe(false);
    expect(config.android?.blockedPermissions).toEqual(BLOCKED_ANDROID_PERMISSIONS);
  });
});

describe("test isolation (R2-7)", () => {
  it("starts every test file without app settings from the developer's shell", () => {
    for (const key of APP_CONFIG_ENV_KEYS) expect(process.env[key]).toBeUndefined();
  });

  it("evaluates Constants.expoConfig from a clean environment", () => {
    const Constants =
      jest.requireMock<typeof import("expo-constants")>("expo-constants").default;
    expect(Constants.expoConfig?.extra).toMatchObject({
      appVariant: "development",
      apiUrl: "http://localhost:8000",
    });
  });

  it("withoutAppConfigEnv drops only app settings", () => {
    expect(
      withoutAppConfigEnv({ PATH: "/bin", APP_VARIANT: "production", EAS_BUILD: "1" }),
    ).toEqual({ PATH: "/bin" });
  });
});
