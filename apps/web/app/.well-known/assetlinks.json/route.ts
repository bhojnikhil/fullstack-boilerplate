import { androidAppLinks } from "@/lib/mobile-associations";

// Read from the running server so signed builds can share the same web image.
export const dynamic = "force-dynamic";

export function GET() {
  const settings = androidAppLinks();
  if (!settings) {
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
          package_name: settings.packageName,
          sha256_cert_fingerprints: settings.fingerprints,
        },
      },
    ],
    { headers: { "Cache-Control": "public, max-age=3600" } },
  );
}
