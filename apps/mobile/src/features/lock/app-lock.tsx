import * as LocalAuthentication from "expo-local-authentication";
import * as SecureStore from "expo-secure-store";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AppState, StyleSheet, View } from "react-native";

import { Button } from "@/components/button";
import { Body, Heading } from "@/components/ui";
import { useSession } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

/** Preference lives in SecureStore so it can't be flipped by editing plain app storage. */
export const APP_LOCK_KEY = "app.lock.enabled";
/** How long the app may be in the background before it asks again. */
export const LOCK_GRACE_MS = 30_000;

export async function isBiometricAvailable(): Promise<boolean> {
  const [hardware, enrolled] = await Promise.all([
    LocalAuthentication.hasHardwareAsync(),
    LocalAuthentication.isEnrolledAsync(),
  ]);
  return hardware && enrolled;
}

async function authenticate(): Promise<boolean> {
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: "Unlock the app",
    cancelLabel: "Cancel",
  });
  return result.success;
}

interface AppLockValue {
  enabled: boolean;
  /** Turning on requires a successful biometric check first. Returns the new state. */
  setEnabled(next: boolean): Promise<boolean>;
}

const AppLockContext = createContext<AppLockValue | null>(null);

export function useAppLock(): AppLockValue {
  const value = useContext(AppLockContext);
  if (!value) throw new Error("useAppLock must be used inside AppLockGate");
  return value;
}

/**
 * Optional biometric lock. Only signed-in sessions are covered. Locks at
 * launch and after the app has been in the background longer than the grace
 * period. The content stays mounted underneath (navigation state survives)
 * but an opaque screen covers it.
 */
export function AppLockGate({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const { colors, spacing } = useTheme();
  const [enabled, setEnabledState] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [locked, setLocked] = useState(true);
  const authenticating = useRef(false);
  const backgroundedAt = useRef<number | null>(null);

  useEffect(() => {
    SecureStore.getItemAsync(APP_LOCK_KEY)
      .then((value) => setEnabledState(value === "1"))
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, []);

  const unlock = useCallback(async () => {
    if (authenticating.current) return;
    authenticating.current = true;
    try {
      if (await authenticate()) setLocked(false);
    } catch {
      // Stay locked; the button tries again.
    } finally {
      authenticating.current = false;
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const subscription = AppState.addEventListener("change", (state) => {
      // The biometric prompt itself backgrounds the app on some platforms.
      if (authenticating.current) return;
      if (state === "background") backgroundedAt.current = Date.now();
      if (state === "active" && backgroundedAt.current !== null) {
        if (Date.now() - backgroundedAt.current > LOCK_GRACE_MS) setLocked(true);
        backgroundedAt.current = null;
      }
    });
    return () => subscription.remove();
  }, [enabled]);

  const showLock = loaded && enabled && locked && status === "signedIn";
  useEffect(() => {
    // unlock() only sets state after the biometric prompt resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (showLock) void unlock();
  }, [showLock, unlock]);

  const setEnabled = useCallback(async (next: boolean) => {
    if (next) {
      if (!(await isBiometricAvailable())) return false;
      authenticating.current = true;
      try {
        if (!(await authenticate())) return false;
      } finally {
        authenticating.current = false;
      }
      await SecureStore.setItemAsync(APP_LOCK_KEY, "1");
    } else {
      await SecureStore.deleteItemAsync(APP_LOCK_KEY);
    }
    setEnabledState(next);
    setLocked(false);
    return next;
  }, []);

  return (
    <AppLockContext.Provider value={{ enabled, setEnabled }}>
      <View style={{ flex: 1 }}>
        {children}
        {showLock ? (
          <View
            testID="app-lock"
            accessibilityViewIsModal
            style={[
              StyleSheet.absoluteFill,
              {
                backgroundColor: colors.background,
                alignItems: "center",
                justifyContent: "center",
                gap: spacing.lg,
                padding: spacing.xl,
              },
            ]}
          >
            <Heading>Locked</Heading>
            <Body>Authenticate to continue.</Body>
            <Button title="Unlock" onPress={() => void unlock()} />
          </View>
        ) : null}
      </View>
    </AppLockContext.Provider>
  );
}
