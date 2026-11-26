import Constants from "expo-constants";

/**
 * The shareable link for an invitation token. With APP_DOMAIN set it is an
 * https App Link (opens the app if installed and verified, else the web
 * page); otherwise it is the custom-scheme link, which only works on devices
 * that already have the app.
 */
export function buildInviteLink(token: string): string {
  const extra = (Constants.expoConfig?.extra ?? {}) as { appDomain?: string };
  const encoded = encodeURIComponent(token);
  if (extra.appDomain) return `https://${extra.appDomain}/invite/${encoded}`;
  const scheme = Constants.expoConfig?.scheme;
  const base = Array.isArray(scheme) ? scheme[0] : scheme;
  return `${base ?? "boilerplate"}://invite/${encoded}`;
}
