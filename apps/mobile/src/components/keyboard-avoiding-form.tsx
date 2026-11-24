import type { ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { useTheme } from "@/theme/use-theme";

interface KeyboardAvoidingFormProps {
  children: ReactNode;
  /**
   * Height of anything above the form that is not part of the keyboard-avoiding
   * view, usually `useHeaderHeight()` from "expo-router/react-navigation"
   * (which already includes the status bar).
   */
  keyboardVerticalOffset?: number;
  contentContainerStyle?: StyleProp<ViewStyle>;
}

/**
 * Keeps focused inputs above the keyboard. With edge-to-edge, Android no
 * longer resizes the window for the keyboard, so `padding` is used on both
 * platforms. The ScrollView keeps taps working while the keyboard is open and
 * lets long forms scroll. For complex forms consider
 * react-native-keyboard-controller (requires a development build).
 */
export function KeyboardAvoidingForm({
  children,
  keyboardVerticalOffset = 0,
  contentContainerStyle,
}: KeyboardAvoidingFormProps) {
  const { spacing } = useTheme();
  return (
    <KeyboardAvoidingView
      behavior="padding"
      keyboardVerticalOffset={keyboardVerticalOffset}
      style={{ flex: 1 }}
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
    </KeyboardAvoidingView>
  );
}
