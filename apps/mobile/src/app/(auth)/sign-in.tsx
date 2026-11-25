import { Link, router } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { ErrorText, Muted, Title } from "@/components/ui";
import { GoogleCancelled, isGoogleSignInAvailable } from "@/features/auth/google";
import { useAuthActions } from "@/features/auth/use-auth-actions";
import { useSubmit } from "@/features/auth/use-submit";
import { ApiError, describeError } from "@/lib/api-error";
import { useTheme } from "@/theme/use-theme";

function describeSignInError(error: unknown): string {
  if (error instanceof GoogleCancelled) return "";
  if (error instanceof ApiError) {
    switch (error.code) {
      case "email_verification_required":
        return "Verify your email first: open the link we sent you, then sign in.";
      case "invalid_credentials":
        return "Wrong email or password.";
      case "google_link_required":
        return "An account with this email already exists. Sign in with your password, then link Google.";
      case "google_email_unverified":
        return "Google says this email isn't verified.";
      case "google_sign_in_disabled":
        return "Google sign-in isn't enabled on this server.";
    }
  }
  return describeError(error);
}

export default function SignIn() {
  const { colors, typography } = useTheme();
  const { signIn, signInWithGoogle } = useAuthActions();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const password$ = useSubmit(signIn, describeSignInError);
  const google$ = useSubmit(signInWithGoogle, describeSignInError);
  const busy = password$.pending || google$.pending;

  const submit = async () => {
    if (await password$.run(email, password)) router.replace("/");
  };

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Title>Welcome back</Title>
        <TextField
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          returnKeyType="next"
        />
        <TextField
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="current-password"
          textContentType="password"
          returnKeyType="done"
          onSubmitEditing={submit}
        />
        <ErrorText message={password$.error ?? google$.error} />
        <Button
          title={password$.pending ? "Signing in…" : "Sign in"}
          disabled={busy || !email || !password}
          onPress={submit}
        />
        {isGoogleSignInAvailable() ? (
          <Button
            title="Continue with Google"
            variant="secondary"
            disabled={busy}
            onPress={async () => {
              if (await google$.run()) router.replace("/");
            }}
          />
        ) : null}
        <Link href="/forgot-password" style={[typography.body, { color: colors.text }]}>
          Forgot your password?
        </Link>
        <Link href="/sign-up" style={[typography.body, { color: colors.text }]}>
          Create an account
        </Link>
        <Muted>
          After creating an account you must verify your email before you can sign in.
        </Muted>
      </KeyboardAvoidingForm>
    </Screen>
  );
}
