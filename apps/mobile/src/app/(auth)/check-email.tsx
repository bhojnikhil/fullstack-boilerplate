import { Link, useLocalSearchParams } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { Body, ErrorText, Muted, Title } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";
import { useTheme } from "@/theme/use-theme";

/** Shown after sign-up: the account can't sign in until the emailed link is opened. */
export default function CheckEmail() {
  const { email } = useLocalSearchParams<{ email?: string }>();
  const { api } = useServices();
  const { colors, typography } = useTheme();
  const [sent, setSent] = useState(false);
  const resend = useSubmit(async () => {
    await unwrap(
      api.POST("/v1/auth/verify-email/resend", { body: { email: email ?? "" } }),
    );
    setSent(true);
  });

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Title>Check your email</Title>
        <Body>
          We sent a link{email ? ` to ${email}` : ""}. Open it on this phone to verify
          your address. You&apos;ll enter the password you just chose to finish.
        </Body>
        <Muted>You can&apos;t sign in until your email is verified.</Muted>
        <ErrorText message={resend.error} />
        {sent ? (
          <Muted accessibilityLiveRegion="polite">Sent. Check your inbox.</Muted>
        ) : null}
        <Button
          title="Resend the email"
          variant="secondary"
          disabled={resend.pending || !email}
          onPress={() => void resend.run()}
        />
        <Link href="/sign-in" style={[typography.body, { color: colors.text }]}>
          Back to sign in
        </Link>
      </KeyboardAvoidingForm>
    </Screen>
  );
}
