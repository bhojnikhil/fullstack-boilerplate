import { appleUniversalLinks } from "@/lib/mobile-associations";

// Read from the running server so signed builds can share the same web image.
export const dynamic = "force-dynamic";

export function GET() {
  const settings = appleUniversalLinks();
  if (!settings) {
    return Response.json(
      { error: "Apple Universal Links are unavailable" },
      { status: 404 },
    );
  }

  return Response.json(
    {
      applinks: {
        details: [
          {
            appIDs: [`${settings.teamId}.${settings.bundleId}`],
            components: settings.paths.map((path) => ({ "/": path })),
          },
        ],
      },
    },
    { headers: { "Cache-Control": "public, max-age=3600" } },
  );
}
