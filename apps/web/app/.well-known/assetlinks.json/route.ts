import { commaSeparated, configuredValue } from "@/lib/public-settings";

// Read from the running server so signed builds can share the same web image.
export const dynamic = "force-dynamic";

const packagePattern = /^[a-z][\w]*(?:\.[a-z][\w]*)+$/i;
const fingerprintPattern = /^(?:[\da-f]{2}:){31}[\da-f]{2}$/i;

export function GET() {
  const packageName = configuredValue("ANDROID_PACKAGE_NAME", (value) =>
    packagePattern.test(value) ? value : undefined,
  );
  const fingerprints = configuredValue("ANDROID_SHA256_CERT_FINGERPRINTS", (value) => {
    const entries = commaSeparated(value).map((entry) => entry.toUpperCase());
    if (entries.length && entries.every((entry) => fingerprintPattern.test(entry))) {
      return [...new Set(entries)];
    }
    return undefined;
  });

  if (!packageName || !fingerprints) {
    return Response.json(
      { error: "Android App Links are unavailable" },
      { status: 404 },
    );
  }

  return Response.json(
    [
      {
        relation: ["delegate_permission/common.handle_all_urls"],
        target: {
          namespace: "android_app",
          package_name: packageName,
          sha256_cert_fingerprints: fingerprints,
        },
      },
    ],
    { headers: { "Cache-Control": "public, max-age=3600" } },
  );
}
