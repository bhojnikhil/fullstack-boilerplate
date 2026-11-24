// Read from the running server so signed builds can share the same web image.
export const dynamic = "force-dynamic";

const teamIdPattern = /^[A-Z0-9]{10}$/;
const bundleIdPattern = /^[a-z0-9-]+(?:\.[a-z0-9-]+)+$/i;

export function GET() {
  const teamId = process.env.IOS_TEAM_ID?.trim();
  const bundleId = process.env.IOS_BUNDLE_ID?.trim();

  if (
    !teamId ||
    !teamIdPattern.test(teamId) ||
    !bundleId ||
    !bundleIdPattern.test(bundleId)
  ) {
    return Response.json(
      { error: "Apple Universal Links are unavailable" },
      { status: 404 },
    );
  }

  return Response.json({
    applinks: {
      details: [
        {
          appIDs: [`${teamId}.${bundleId}`],
          components: [{ "/": "/app/*" }],
        },
      ],
    },
  });
}
