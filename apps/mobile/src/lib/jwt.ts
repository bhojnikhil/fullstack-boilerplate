export interface AccessClaims {
  /** Session id: the identity a request and its refresh are bound to. */
  sid: string;
  /** Account (user) id. */
  sub: string;
}

/**
 * Reads the claims of an access token WITHOUT verifying it (the API verifies
 * it on every request). Used only to learn which session/account the token
 * belongs to. Returns null for anything that isn't a well-formed JWT.
 */
export function decodeAccessClaims(token: string): AccessClaims | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const json = globalThis.atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
    const claims: unknown = JSON.parse(json);
    if (typeof claims !== "object" || claims === null) return null;
    const { sid, sub } = claims as Record<string, unknown>;
    if (typeof sid !== "string" || typeof sub !== "string" || !sid || !sub) return null;
    return { sid, sub };
  } catch {
    return null;
  }
}
