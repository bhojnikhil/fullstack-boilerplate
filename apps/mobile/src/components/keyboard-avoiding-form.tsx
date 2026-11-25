import type { ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { useOfflineBannerHeight } from "@/components/network-banner";
import { useTheme } from "@/theme/use-theme";

interface KeyboardAvoidingFormProps {
  children: ReactNode;
  /**
   * Height of anything above the form that is not part of the keyboard-avoiding
   * view, usually `useHeaderHeight()` from "expo-router/react-navigation"
   * (which already includes the status bar). The offline banner's height is
   * added automatically.
   */
  keyboardVerticalOffset?: number;
  contentContainerStyle?: StyleProp<ViewStyle>;
}

/** The given offset plus the offline banner's height while it is visible. */
export function useKeyboardVerticalOffset(offset: number): number {
  return offset + useOfflineBannerHeight();
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
  const offset = useKeyboardVerticalOffset(keyboardVerticalOffset);
  return (
    <KeyboardAvoidingView
      behavior="padding"
      keyboardVerticalOffset={offset}
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
