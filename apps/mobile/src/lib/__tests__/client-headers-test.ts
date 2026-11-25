import { buildClientHeaders } from "../client-headers";

describe("client headers", () => {
  it.each(["android", "ios"])("builds headers for %s", (platform) => {
    expect(buildClientHeaders({ appVersion: "1.4.0", platform })).toEqual({
      "X-App-Version": "1.4.0",
      "X-Platform": platform,
    });
  });

  it("rejects unsupported platforms", () => {
    expect(() => buildClientHeaders({ appVersion: "1.0.0", platform: "web" })).toThrow(
      /Unsupported platform/,
    );
  });

  it.each([undefined, null, "", "1.0", "v1.0.0", "1.0.0-beta"])(
    "rejects version %p",
    (appVersion) => {
      expect(() => buildClientHeaders({ appVersion, platform: "ios" })).toThrow(
        /MAJOR.MINOR.PATCH/,
      );
    },
  );
});
