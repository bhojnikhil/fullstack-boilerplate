// Read from the running server so signed builds can share the same web image.
export const dynamic = "force-dynamic";

const packagePattern = /^[a-z][\w]*(?:\.[a-z][\w]*)+$/i;
const fingerprintPattern = /^(?:[\da-f]{2}:){31}[\da-f]{2}$/i;

export function GET() {
  const packageName = process.env.ANDROID_PACKAGE_NAME?.trim();
  const fingerprints = process.env.ANDROID_SHA256_CERT_FINGERPRINTS?.split(",").map(
    (value) => value.trim().toUpperCase(),
  );

  if (
    !packageName ||
    !packagePattern.test(packageName) ||
    !fingerprints?.every((value) => fingerprintPattern.test(value))
  ) {
    return Response.json(
      { error: "Android App Links are unavailable" },
      { status: 404 },
    );
  }

  return Response.json([
    {
      relation: ["delegate_permission/common.handle_all_urls"],
      target: {
        namespace: "android_app",
        package_name: packageName,
        sha256_cert_fingerprints: fingerprints,
      },
    },
  ]);
}
