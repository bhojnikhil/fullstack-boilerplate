import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Keyboard,
  Platform,
  ScrollView,
  View,
  type HostInstance,
  type KeyboardEvent,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { measureInWindow, type WindowFrame } from "@/components/measure-in-window";
import { useTheme } from "@/theme/use-theme";

/** How far the keyboard (top edge at `keyboardTop`, window coordinates) covers `frame`. */
export function keyboardOverlap(
  frame: WindowFrame,
  keyboardTop: number | null,
): number {
  if (keyboardTop === null) return 0;
  return Math.max(0, Math.round(frame.y + frame.height - keyboardTop));
}

interface KeyboardAvoidingFormProps {
  children: ReactNode;
  contentContainerStyle?: StyleProp<ViewStyle>;
}

/**
 * Keeps focused inputs above the keyboard.
 *
 * With edge-to-edge, Android no longer resizes the window for the keyboard,
 * so the form pads itself by however much the keyboard overlaps it. The
 * overlap is measured in window coordinates (the form's bottom edge vs the
 * keyboard's top edge), so headers, the offline banner or anything else above
 * the form need no offset. It is recomputed on every keyboard event and on
 * every layout change of the form, e.g. when the offline banner appears while
 * the keyboard is open. (React Native's KeyboardAvoidingView measures relative
 * to its parent and only re-reads keyboardVerticalOffset on its next keyboard
 * or height change.) The ScrollView keeps taps working while the keyboard is
 * open and lets long forms scroll. For complex forms consider
 * react-native-keyboard-controller (requires a development build).
 */
export function KeyboardAvoidingForm({
  children,
  contentContainerStyle,
}: KeyboardAvoidingFormProps) {
  const { spacing } = useTheme();
  const ref = useRef<HostInstance>(null);
  const keyboardTop = useRef<number | null>(null);
  const [inset, setInset] = useState(0);

  const update = useCallback(() => {
    const top = keyboardTop.current;
    if (top === null) {
      setInset(0);
      return;
    }
    measureInWindow(ref, (frame) => setInset(keyboardOverlap(frame, top)));
  }, []);

  useEffect(() => {
    const onShow = (event: KeyboardEvent) => {
      keyboardTop.current = event.endCoordinates.screenY;
      update();
    };
    const onHide = () => {
      keyboardTop.current = null;
      update();
    };
    const subscriptions =
      Platform.OS === "ios"
        ? [
            Keyboard.addListener("keyboardWillChangeFrame", onShow),
            Keyboard.addListener("keyboardWillHide", onHide),
          ]
        : [
            Keyboard.addListener("keyboardDidShow", onShow),
            Keyboard.addListener("keyboardDidHide", onHide),
          ];
    // Mounted while the keyboard is already open (e.g. after navigation).
    const metrics = Keyboard.isVisible() ? Keyboard.metrics() : undefined;
    if (metrics) {
      keyboardTop.current = metrics.screenY;
      update();
    }
    return () => subscriptions.forEach((subscription) => subscription.remove());
  }, [update]);

  return (
    <View
      ref={ref}
      testID="keyboard-avoiding-form"
      onLayout={update}
      style={{ flex: 1, paddingBottom: inset }}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode={Platform.OS === "ios" ? "interactive" : "on-drag"}
        contentContainerStyle={[
          { flexGrow: 1, padding: spacing.xl, gap: spacing.lg },
          contentContainerStyle,
        ]}
      >
        {children}
      </ScrollView>
    </View>
  );
}
