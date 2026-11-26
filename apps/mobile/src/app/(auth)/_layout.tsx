import { Stack } from "expo-router";

// Opening /sign-up directly (e.g. from a deep link) still puts sign-in
// underneath it, so back goes to sign-in instead of leaving the app.
export const unstable_settings = { anchor: "sign-in" };

export default function AuthLayout() {
  return (
    <Stack>
      <Stack.Screen name="sign-in" options={{ title: "Sign in" }} />
      <Stack.Screen name="sign-up" options={{ title: "Create account" }} />
      <Stack.Screen name="check-email" options={{ title: "Check your email" }} />
      <Stack.Screen name="forgot-password" options={{ title: "Reset password" }} />
    </Stack>
  );
}
