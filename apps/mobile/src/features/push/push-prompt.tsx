import AsyncStorage from "@react-native-async-storage/async-storage";
import { useEffect, useState } from "react";

import { Button } from "@/components/button";
import { Body, Card, ErrorText, Heading } from "@/components/ui";
import { describeError } from "@/lib/api-error";
import { useServices, useSession } from "@/providers/services";

import { getPushPermission, registerPushDevice, requestPushPermission } from "./push";

const DISMISSED_PREFIX = "push-prompt-dismissed:";

/**
 * Asks for notification permission in context: a dismissible card on the
 * items tab, shown after the user is signed in and looking at their data,
 * never at launch or on the sign-in screen. The OS prompt only appears after
 * the person taps "Turn on".
 */
export function PushPrompt() {
  const { api } = useServices();
  const { accountId } = useSession();
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accountId) return;
    let cancelled = false;
    Promise.all([
      getPushPermission(),
      AsyncStorage.getItem(`${DISMISSED_PREFIX}${accountId}`),
    ])
      .then(([permission, dismissed]) => {
        if (!cancelled) setVisible(permission === "undetermined" && dismissed === null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  if (!visible || !accountId) return null;
  const dismiss = () => {
    setVisible(false);
    AsyncStorage.setItem(`${DISMISSED_PREFIX}${accountId}`, "1").catch(() => undefined);
  };
  return (
    <Card>
      <Heading>Stay in the loop</Heading>
      <Body>Get a notification when something changes in your workspace.</Body>
      <ErrorText message={error} />
      <Button
        title="Turn on notifications"
        onPress={async () => {
          try {
            if (await requestPushPermission()) await registerPushDevice(api);
            dismiss();
          } catch (caught) {
            setError(describeError(caught));
          }
        }}
      />
      <Button title="Not now" variant="secondary" onPress={dismiss} />
    </Card>
  );
}
