import { runtimeVersionFor } from "../app.config";
import {
  envForPull,
  parseDotenv,
  parseReleaseTarget,
  planReleaseUpdate,
  type ReleaseTarget,
} from "../scripts/release-update";

const PROJECT = "123e4567-e89b-12d3-a456-426614174000";

function hostedFor(
  target: ReleaseTarget,
  overrides: Record<string, string | undefined> = {},
) {
  const base: Record<string, string> = {
    APP_VARIANT: target,
    API_URL: `https://api-${target}.acme.dev`,
    EAS_PROJECT_ID: PROJECT,
    EXPO_OWNER: "acme",
    ...(target === "production"
      ? { ANDROID_PACKAGE: "dev.acme.app", IOS_BUNDLE_ID: "dev.acme.app" }
      : {}),
  };
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) delete base[key];
    else base[key] = value;
  }
  return base;
}

/** A developer shell with stale release settings in it. */
const SHELL = {
  PATH: "/usr/bin",
  EXPO_TOKEN: "token",
  EAS_PROJECT_ID: PROJECT,
  APP_VARIANT: "production",
  API_URL: "https://api-production.acme.dev",
  APP_DOMAIN: "shell.acme.dev",
  APP_LINK_PATHS: "/invite/",
};

describe("parseReleaseTarget", () => {
  it.each(["preview", "production"])("accepts %s", (target) => {
    expect(parseReleaseTarget(target)).toBe(target);
  });

  it.each([undefined, "", "development", "prod", "staging"])("rejects %p", (target) => {
    expect(() => parseReleaseTarget(target)).toThrow(/Usage: pnpm release:update/);
  });
});

describe("parseDotenv", () => {
  it("reads eas env:pull output", () => {
    expect(
      parseDotenv(
        "# Environment: preview\n\nAPP_VARIANT=preview\nAPI_URL=https://a.dev/x=y\n# TOKEN=***** (secret)\n\n",
      ),
    ).toEqual({ APP_VARIANT: "preview", API_URL: "https://a.dev/x=y" });
  });
});

describe("envForPull", () => {
  it("evaluates as development with only the project from the shell", () => {
    const env = envForPull(SHELL);
    expect(env).toMatchObject({ APP_VARIANT: "development", EAS_PROJECT_ID: PROJECT });
    expect(env.API_URL).toBeUndefined();
    expect(env.APP_DOMAIN).toBeUndefined();
    expect(env.EXPO_TOKEN).toBe("token");
  });

  it("needs EAS_PROJECT_ID", () => {
    expect(() => envForPull({ PATH: "/usr/bin" })).toThrow(/Export EAS_PROJECT_ID/);
  });
});

describe("planReleaseUpdate (R2-1)", () => {
  it.each(["preview", "production"] as const)(
    "derives channel, environment and variant from the one target: %s",
    (target) => {
      const plan = planReleaseUpdate({
        target,
        hosted: hostedFor(target),
        shellEnv: SHELL,
        message: "Fix",
      });
      expect(plan.args).toEqual([
        "update",
        "--channel",
        target,
        "--environment",
        target,
        "--message",
        "Fix",
        "--non-interactive",
      ]);
      expect(plan.runtimeVersion).toBe(runtimeVersionFor(target));
      expect(plan.apiUrl).toBe(`https://api-${target}.acme.dev`);
      expect(plan.env).toMatchObject({ APP_VARIANT: target, EXPO_TOKEN: "token" });
    },
  );

  it("ignores release settings left in the shell", () => {
    const plan = planReleaseUpdate({
      target: "preview",
      hosted: hostedFor("preview"),
      shellEnv: SHELL,
      message: "Fix",
    });
    expect(plan.env.APP_VARIANT).toBe("preview");
    expect(plan.env.API_URL).toBe("https://api-preview.acme.dev");
    expect(plan.env.APP_DOMAIN).toBeUndefined();
    expect(plan.env.APP_LINK_PATHS).toBeUndefined();
  });

  it.each<[string, ReleaseTarget, Record<string, string | undefined>, RegExp]>([
    // The reviewer's case: hosted env without APP_VARIANT, shell says production.
    [
      "hosted APP_VARIANT missing",
      "production",
      { APP_VARIANT: undefined },
      /has no APP_VARIANT/,
    ],
    [
      "hosted APP_VARIANT for another variant",
      "production",
      { APP_VARIANT: "development" },
      /APP_VARIANT=development; it must be production/,
    ],
    [
      "hosted APP_VARIANT invalid",
      "preview",
      { APP_VARIANT: "s3cr3t" },
      /an invalid APP_VARIANT/,
    ],
    ["hosted API_URL missing", "preview", { API_URL: undefined }, /has no API_URL/],
    [
      "hosted API_URL not https",
      "production",
      { API_URL: "http://api.acme.dev" },
      /https:\/\//,
    ],
    [
      "hosted EAS_PROJECT_ID missing",
      "preview",
      { EAS_PROJECT_ID: undefined },
      /has no EAS_PROJECT_ID/,
    ],
    [
      "hosted project differs from shell",
      "preview",
      { EAS_PROJECT_ID: "00000000-0000-0000-0000-000000000000" },
      /different EAS_PROJECT_ID/,
    ],
    [
      "production ids missing",
      "production",
      { ANDROID_PACKAGE: undefined },
      /ANDROID_PACKAGE is required/,
    ],
  ])("refuses to publish: %s", (_name, target, overrides, message) => {
    expect(() =>
      planReleaseUpdate({
        target,
        hosted: hostedFor(target, overrides),
        shellEnv: SHELL,
        message: "Fix",
      }),
    ).toThrow(message);
  });

  it("never echoes an invalid hosted variant", () => {
    expect(() =>
      planReleaseUpdate({
        target: "preview",
        hosted: hostedFor("preview", { APP_VARIANT: "s3cr3t" }),
        shellEnv: SHELL,
        message: "Fix",
      }),
    ).toThrow(
      expect.objectContaining({ message: expect.not.stringContaining("s3cr3t") }),
    );
  });

  it("requires a message", () => {
    expect(() =>
      planReleaseUpdate({
        target: "preview",
        hosted: hostedFor("preview"),
        shellEnv: SHELL,
        message: " ",
      }),
    ).toThrow(/release message is required/);
  });
});
