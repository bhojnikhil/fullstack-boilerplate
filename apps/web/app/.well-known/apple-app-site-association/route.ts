import { commaSeparated, configuredValue } from "@/lib/public-settings";

// Read from the running server so signed builds can share the same web image.
export const dynamic = "force-dynamic";

const teamIdPattern = /^[A-Z0-9]{10}$/;
const bundleIdPattern = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/i;
const pathPattern = /^\/(?:[a-z0-9_.*~-]+\/)*[a-z0-9_.*~-]*$/i;

export function GET() {
  const teamId = configuredValue("IOS_TEAM_ID", (value) => {
    const upper = value.toUpperCase();
    return teamIdPattern.test(upper) ? upper : undefined;
  });
  const bundleId = configuredValue("IOS_BUNDLE_ID", (value) =>
    bundleIdPattern.test(value) ? value : undefined,
  );
  const configuredPaths = configuredValue("IOS_APPLINK_PATHS", (value) => {
    const entries = commaSeparated(value);
    if (
      entries.length &&
      entries.every(
        (entry) =>
          pathPattern.test(entry) &&
          !entry.split("/").some((part) => part === "." || part === ".."),
      )
    ) {
      return [...new Set(entries)];
    }
    return undefined;
  });
  const paths = process.env.IOS_APPLINK_PATHS?.trim() ? configuredPaths : ["/app/*"];

  if (!teamId || !bundleId || !paths) {
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
            appIDs: [`${teamId}.${bundleId}`],
            components: paths.map((path) => ({ "/": path })),
          },
        ],
      },
    },
    { headers: { "Cache-Control": "public, max-age=3600" } },
  );
}
