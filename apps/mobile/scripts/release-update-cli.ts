/**
 * pnpm release:update <preview|production> --message "<message>"
 *
 * Publishes an EAS Update whose channel, EAS environment and app variant all
 * come from the one target argument, after checking the hosted environment
 * (see release-update.ts). Run from apps/mobile; needs `pnpm exec eas login`
 * and EAS_PROJECT_ID / EXPO_OWNER exported.
 */
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  envForPull,
  parseDotenv,
  parseReleaseTarget,
  planReleaseUpdate,
} from "./release-update.ts";

function eas(args: string[], env: NodeJS.ProcessEnv): number {
  const result = spawnSync("pnpm", ["exec", "eas", ...args], { stdio: "inherit", env });
  return result.status ?? 1;
}

function main(argv: string[]): number {
  const target = parseReleaseTarget(argv[0]);
  const messageIndex = argv.indexOf("--message");
  const message = messageIndex >= 0 ? (argv[messageIndex + 1] ?? "") : "";

  // Read the hosted environment into a private temp dir, then delete it.
  const dir = mkdtempSync(path.join(tmpdir(), "eas-env-"));
  let hosted: Record<string, string>;
  try {
    const file = path.join(dir, ".env");
    const pullArgs = [
      "env:pull",
      "--environment",
      target,
      "--path",
      file,
      "--non-interactive",
    ];
    const status = eas(pullArgs, envForPull(process.env) as NodeJS.ProcessEnv);
    if (status !== 0) return status;
    hosted = parseDotenv(readFileSync(file, "utf8"));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }

  const plan = planReleaseUpdate({ target, hosted, shellEnv: process.env, message });
  console.log(
    `Publishing: channel ${plan.target}, EAS environment ${plan.target}, ` +
      `runtime ${plan.runtimeVersion}, API ${plan.apiUrl}`,
  );
  return eas(plan.args, plan.env as NodeJS.ProcessEnv);
}

try {
  process.exitCode = main(process.argv.slice(2));
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
