import { randomUUID } from "expo-crypto";

/**
 * RFC 4122 v4 id. Hermes has no global `crypto.randomUUID`, so expo-crypto
 * (native) is the source on device; the global is used where it exists.
 */
export function uuid(): string {
  const web = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  return web?.randomUUID ? web.randomUUID() : randomUUID();
}
