import { router } from "expo-router";
import { useState } from "react";

import { Button } from "@/components/button";
import { KeyboardAvoidingForm } from "@/components/keyboard-avoiding-form";
import { Screen } from "@/components/screen";
import { TextField } from "@/components/text-field";
import { ErrorText, Title } from "@/components/ui";
import { useSubmit } from "@/features/auth/use-submit";
import { useDiscardChangesGuard } from "@/hooks/use-discard-changes-guard";
import { unwrap } from "@/lib/api-error";
import { useServices } from "@/providers/services";

export default function SignUp() {
  const { api } = useServices();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);

  // Android back (and header back / iOS swipe) asks before discarding input,
  // but not once the account was requested.
  useDiscardChangesGuard(
    !done && (name !== "" || email !== "" || password !== ""),
    () => {
      setName("");
      setEmail("");
      setPassword("");
    },
  );

  const register = useSubmit(async () => {
    await unwrap(
      api.POST("/v1/auth/register", {
        body: { name: name.trim(), email: email.trim(), password },
      }),
    );
  });

  const submit = async () => {
    if (!(await register.run())) return;
    // The password is never carried to the next screen: verifying needs it
    // again (see the verify-email screen).
    setDone(true);
    setPassword("");
    router.replace({ pathname: "/check-email", params: { email: email.trim() } });
  };

  return (
    <Screen edges={["bottom", "left", "right"]}>
      <KeyboardAvoidingForm>
        <Title>Create your account</Title>
        <TextField
          label="Name"
          value={name}
          onChangeText={setName}
          autoComplete="name"
          textContentType="name"
          returnKeyType="next"
        />
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
          autoComplete="new-password"
          textContentType="newPassword"
          returnKeyType="done"
          hint="Use a long, unique password. Remember it: you'll enter it again to verify your email."
        />
        <ErrorText message={register.error} />
        <Button
          title={register.pending ? "Creating…" : "Create account"}
          disabled={register.pending || !name || !email || !password}
          onPress={submit}
        />
      </KeyboardAvoidingForm>
    </Screen>
  );
}
