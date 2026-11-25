import NetInfo, {
  useNetInfo,
  type NetInfoState,
} from "@react-native-community/netinfo";
import { focusManager, onlineManager } from "@tanstack/react-query";
import { AppState, Platform, type AppStateStatus } from "react-native";

type Connectivity = Pick<NetInfoState, "isConnected" | "isInternetReachable">;

/**
 * Offline only when NetInfo is sure: `null` means "not known yet" (e.g. at
 * startup), which is treated as online so the banner doesn't flash.
 */
export function isOffline(state: Connectivity): boolean {
  return state.isConnected === false || state.isInternetReachable === false;
}

export function useIsOffline(): boolean {
  return isOffline(useNetInfo());
}

/**
 * Lets TanStack Query pause/resume with connectivity and refetch when the app
 * returns to the foreground. On foreground, NetInfo is asked to re-check:
 * connectivity can change while the app is suspended without an event
 * reaching JS, which would leave a stale banner or paused queries. Returns a
 * cleanup function.
 */
export function connectQueryManagers(): () => void {
  onlineManager.setEventListener((setOnline) =>
    NetInfo.addEventListener((state) => setOnline(!isOffline(state))),
  );

  const subscription = AppState.addEventListener("change", (status: AppStateStatus) => {
    const active = status === "active";
    if (Platform.OS !== "web") focusManager.setFocused(active);
    // refresh() notifies NetInfo listeners (useNetInfo, onlineManager) with
    // the fresh state.
    if (active) NetInfo.refresh().catch(() => undefined);
  });
  return () => {
    subscription.remove();
    // Stop listening to NetInfo; TanStack falls back to assuming online.
    onlineManager.setEventListener(() => undefined);
  };
}
