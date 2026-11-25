import { useCallback } from "react";
import { Platform } from "react-native";
import * as Device from "expo-device";

import { unwrap } from "@/lib/api-error";
import { useClearQueryCache } from "@/providers/app-providers";
import { useServices } from "@/providers/services";
import { unregisterPushDevice } from "@/features/push/push";
import { useMutationQueueOptional } from "@/features/items/queue-provider";

import { getGoogleIdToken, googleSignOutQuietly } from "./google";

function deviceName(): string {
  return Device.deviceName ?? Device.modelName ?? `${Platform.OS} device`;
}

export function useAuthActions() {
  const { api, session } = useServices();
  const clearQueryCache = useClearQueryCache();
  const queue = useMutationQueueOptional();

  const signIn = useCallback(
    async (email: string, password: string) => {
      const tokens = await unwrap(
        api.POST("/v1/auth/login", {
          body: { email: email.trim(), password, device_name: deviceName() },
        }),
      );
      await session.signIn({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token ?? "",
      });
    },
    [api, session],
  );

  const signInWithGoogle = useCallback(async () => {
    const idToken = await getGoogleIdToken();
    const tokens = await unwrap(
      api.POST("/v1/auth/google", {
        body: { id_token: idToken, device_name: deviceName() },
      }),
    );
    await session.signIn({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token ?? "",
    });
  }, [api, session]);

  /** Ends this session on the server (best effort) and wipes everything local. */
  const signOut = useCallback(async () => {
    await unregisterPushDevice(api).catch(() => undefined);
    await api.POST("/v1/auth/logout").catch(() => undefined);
    await queue?.clear();
    await googleSignOutQuietly();
    // Cache first: signing out switches the cache scope, which unmounts it.
    await clearQueryCache().catch(() => undefined);
    await session.signOut();
  }, [api, clearQueryCache, queue, session]);

  /** After the server has deleted the account: only local cleanup is left. */
  const forgetLocally = useCallback(async () => {
    await queue?.clear();
    await googleSignOutQuietly();
    await clearQueryCache().catch(() => undefined);
    await session.signOut();
  }, [clearQueryCache, queue, session]);

  return { signIn, signInWithGoogle, signOut, forgetLocally };
}
