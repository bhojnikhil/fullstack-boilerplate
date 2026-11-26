import { makeAccessToken } from "../../../test-utils/fake-api";
import { decodeAccessClaims } from "../jwt";

describe("decodeAccessClaims", () => {
  it("reads the session and account ids", () => {
    expect(decodeAccessClaims(makeAccessToken("s", "u"))).toEqual({
      sid: "s",
      sub: "u",
    });
  });
  it.each(["", "abc", "a.b.c", "a..c"])("rejects %j", (token) => {
    expect(decodeAccessClaims(token)).toBeNull();
  });
});
