import { unwrap } from "@/lib/api-error";
import type { AppServices } from "@/lib/app-services";

/**
 * PROVISIONAL contract for workspaces, members and invitations.
 *
 * Phase 5 (workspaces) is not on this branch, so these endpoints are NOT in
 * the generated client. The shapes below follow the v2 spec ("Multi-tenancy")
 * and are an assumption until phase 5 lands: then regenerate the client
 * (`make gen-client`), delete this file and call the typed `api` directly.
 * The one unchecked cast is isolated here on purpose.
 */
export type Role = "owner" | "admin" | "member";

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  currency: string;
  timezone: string;
  role: Role;
}

export interface Member {
  user_id: string;
  name: string;
  /** Only admins and the owner see other members' addresses; null otherwise. */
  email: string | null;
  role: Role;
}

export interface Invitation {
  /** The one-time secret in the invite link. */
  token: string;
  expires_at: string;
}

interface LooseResult {
  data?: unknown;
  error?: unknown;
  response: Response;
}
interface LooseClient {
  GET(path: string, init?: object): Promise<LooseResult>;
  POST(path: string, init?: object): Promise<LooseResult>;
  DELETE(path: string, init?: object): Promise<LooseResult>;
}

export function workspaceApi(api: AppServices["api"]) {
  const client = api as unknown as LooseClient;
  const call = <T>(result: Promise<LooseResult>) =>
    unwrap(result as Promise<{ data?: T; error?: unknown; response: Response }>);
  return {
    list: async () => {
      const page = await call<{ items: Workspace[] }>(client.GET("/v1/workspaces"));
      return page.items;
    },
    create: (body: { name: string; currency: string; timezone: string }) =>
      call<Workspace>(client.POST("/v1/workspaces", { body })),
    members: async (workspaceId: string) => {
      const page = await call<{ items: Member[] }>(
        client.GET(`/v1/workspaces/${encodeURIComponent(workspaceId)}/members`),
      );
      return page.items;
    },
    removeMember: (workspaceId: string, userId: string) =>
      call<void>(
        client.DELETE(
          `/v1/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`,
        ),
      ),
    invite: (workspaceId: string, role: Role) =>
      call<Invitation>(
        client.POST(`/v1/workspaces/${encodeURIComponent(workspaceId)}/invitations`, {
          body: { role },
        }),
      ),
    acceptInvitation: (token: string) =>
      call<Workspace>(client.POST("/v1/invitations/accept", { body: { token } })),
  };
}
