import { useQuery } from "@tanstack/react-query";

import { unwrap } from "@/lib/api-error";
import { useServices, useSession } from "@/providers/services";

/** The signed-in user's profile. Not persisted to disk: it holds the email address. */
export function useProfile() {
  const { api } = useServices();
  const { accountId } = useSession();
  return useQuery({
    queryKey: ["profile", accountId],
    enabled: accountId !== null,
    queryFn: () => unwrap(api.GET("/v1/me")),
  });
}
