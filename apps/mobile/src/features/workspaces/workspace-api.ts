import type { components } from "@repo/api-client";
import { unwrap } from "@/lib/api-error";
import type { AppServices } from "@/lib/app-services";

export type Role = components["schemas"]["InvitableRole"];

export function workspaceApi(api: AppServices["api"]) {
  const path = (workspace_id: string) => ({ path: { workspace_id } });
  return {
    list: async () => {
      const items: components["schemas"]["WorkspaceResponse"][] = [];
      let cursor: string | null = null;
      do {
        const page = await unwrap(
          api.GET("/v1/workspaces", { params: { query: { cursor } } }),
        );
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
    create: (body: components["schemas"]["WorkspaceCreate"]) =>
      unwrap(api.POST("/v1/workspaces", { body })),
    rename: (id: string, name: string) =>
      unwrap(
        api.PATCH("/v1/workspaces/{workspace_id}", {
          params: path(id),
          body: { name },
        }),
      ),
    leave: (id: string) =>
      unwrap(api.POST("/v1/workspaces/{workspace_id}/leave", { params: path(id) })),
    delete: (id: string) =>
      unwrap(api.DELETE("/v1/workspaces/{workspace_id}", { params: path(id) })),
    transfer: (id: string, user_id: string) =>
      unwrap(
        api.POST("/v1/workspaces/{workspace_id}/transfer-ownership", {
          params: path(id),
          body: { user_id },
        }),
      ),
    members: async (id: string) => {
      const items: components["schemas"]["MemberResponse"][] = [];
      let cursor: string | null = null;
      do {
        const page = await unwrap(
          api.GET("/v1/workspaces/{workspace_id}/members", {
            params: { ...path(id), query: { cursor } },
          }),
        );
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
    removeMember: (workspace_id: string, user_id: string) =>
      unwrap(
        api.DELETE("/v1/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id, user_id } },
        }),
      ),
    changeRole: (workspace_id: string, user_id: string, role: Role) =>
      unwrap(
        api.PATCH("/v1/workspaces/{workspace_id}/members/{user_id}", {
          params: { path: { workspace_id, user_id } },
          body: { role },
        }),
      ),
    invite: (id: string, role: Role, email?: string) =>
      unwrap(
        api.POST("/v1/workspaces/{workspace_id}/invitations", {
          params: path(id),
          body: { role, email: email || null },
        }),
      ),
    invitations: async (id: string) => {
      const items: components["schemas"]["InvitationResponse"][] = [];
      let cursor: string | null = null;
      do {
        const page = await unwrap(
          api.GET("/v1/workspaces/{workspace_id}/invitations", {
            params: { ...path(id), query: { cursor } },
          }),
        );
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items;
    },
    revoke: (workspace_id: string, invitation_id: string) =>
      unwrap(
        api.DELETE("/v1/workspaces/{workspace_id}/invitations/{invitation_id}", {
          params: { path: { workspace_id, invitation_id } },
        }),
      ),
    acceptInvitation: (token: string) =>
      unwrap(api.POST("/v1/invitations/accept", { body: { token } })),
  };
}
