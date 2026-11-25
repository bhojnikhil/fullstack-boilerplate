import { PHASE_PRODUCTION_BUILD } from "next/constants";

export async function register() {
  if (
    process.env.NEXT_RUNTIME !== "nodejs" ||
    process.env.NEXT_PHASE === PHASE_PRODUCTION_BUILD
  ) {
    return;
  }

  const { androidAppLinks, appleUniversalLinks } =
    await import("@/lib/mobile-associations");
  const { supportEmail } = await import("@/lib/public-settings");
  supportEmail();
  androidAppLinks();
  appleUniversalLinks();
}
