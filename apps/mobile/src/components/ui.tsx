import { Text, View, type TextProps } from "react-native";

import { useTheme } from "@/theme/use-theme";

export function Title({ children, ...props }: TextProps) {
  const { colors, typography } = useTheme();
  return (
    <Text
      accessibilityRole="header"
      style={[typography.title, { color: colors.text }]}
      {...props}
    >
      {children}
    </Text>
  );
}

export function Heading({ children, ...props }: TextProps) {
  const { colors, typography } = useTheme();
  return (
    <Text
      accessibilityRole="header"
      style={[typography.heading, { color: colors.text }]}
      {...props}
    >
      {children}
    </Text>
  );
}

export function Body({ children, ...props }: TextProps) {
  const { colors, typography } = useTheme();
  return (
    <Text style={[typography.body, { color: colors.text }]} {...props}>
      {children}
    </Text>
  );
}

export function Muted({ children, ...props }: TextProps) {
  const { colors, typography } = useTheme();
  return (
    <Text style={[typography.caption, { color: colors.textMuted }]} {...props}>
      {children}
    </Text>
  );
}

/** A form-level error, announced to screen readers when it appears. */
export function ErrorText({ message }: { message: string | null | undefined }) {
  const { colors, typography } = useTheme();
  if (!message) return null;
  return (
    <Text
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      style={[typography.body, { color: colors.danger }]}
    >
      {message}
    </Text>
  );
}

export function Card({ children }: { children: React.ReactNode }) {
  const { colors, spacing, radius } = useTheme();
  return (
    <View
      style={{
        backgroundColor: colors.surface,
        borderRadius: radius.md,
        padding: spacing.lg,
        gap: spacing.sm,
      }}
    >
      {children}
    </View>
  );
}
