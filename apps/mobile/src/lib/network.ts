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
 * returns to the foreground. Returns a cleanup function.
 */
export function connectQueryManagers(): () => void {
  onlineManager.setEventListener((setOnline) =>
    NetInfo.addEventListener((state) => setOnline(!isOffline(state))),
  );

  const subscription = AppState.addEventListener("change", (status: AppStateStatus) => {
    if (Platform.OS !== "web") focusManager.setFocused(status === "active");
  });
  return () => subscription.remove();
}
