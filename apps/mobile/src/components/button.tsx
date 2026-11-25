import { Pressable, Text, type PressableProps } from "react-native";

import { MIN_TOUCH_TARGET } from "@/theme/tokens";
import { useTheme } from "@/theme/use-theme";

interface ButtonProps extends Omit<PressableProps, "children" | "style"> {
  title: string;
  variant?: "primary" | "secondary";
}

export function Button({
  title,
  variant = "primary",
  disabled,
  ...props
}: ButtonProps) {
  const { colors, spacing, radius, typography } = useTheme();
  const primary = variant === "primary";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      style={({ pressed }) => ({
        minHeight: MIN_TOUCH_TARGET,
        justifyContent: "center",
        alignItems: "center",
        paddingHorizontal: spacing.lg,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: primary ? colors.primary : colors.controlBorder,
        backgroundColor: primary ? colors.primary : colors.background,
        opacity: disabled ? 0.5 : pressed ? 0.8 : 1,
      })}
      {...props}
    >
      <Text
        style={[typography.label, { color: primary ? colors.onPrimary : colors.text }]}
      >
        {title}
      </Text>
    </Pressable>
  );
}
