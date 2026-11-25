import Constants from "expo-constants";

import { buildInviteLink } from "../invite-link";

describe("buildInviteLink", () => {
  it("uses the custom scheme without an app domain, encoding the token", () => {
    expect(buildInviteLink("a/b c")).toBe("boilerplate-dev://invite/a%2Fb%20c");
  });

  it("uses the https App Link when APP_DOMAIN is configured", () => {
    const extra = Constants.expoConfig!.extra as Record<string, unknown>;
    extra.appDomain = "app.example.com";
    try {
      expect(buildInviteLink("tok")).toBe("https://app.example.com/invite/tok");
    } finally {
      delete extra.appDomain;
    }
  });
});
