import { useId } from "react";
import { Text, TextInput, View, type TextInputProps } from "react-native";

import { MIN_TOUCH_TARGET } from "@/theme/tokens";
import { useTheme } from "@/theme/use-theme";

interface TextFieldProps extends Omit<TextInputProps, "style"> {
  label: string;
  /** Shown below the input and announced to screen readers. */
  error?: string;
  hint?: string;
}

/** Labelled text input. The label doubles as the accessibility label. */
export function TextField({ label, error, hint, ...inputProps }: TextFieldProps) {
  const { colors, spacing, radius, typography } = useTheme();
  const labelId = useId();
  return (
    <View style={{ gap: spacing.xs }}>
      <Text nativeID={labelId} style={[typography.label, { color: colors.text }]}>
        {label}
      </Text>
      <TextInput
        accessibilityLabel={label}
        accessibilityLabelledBy={labelId}
        accessibilityHint={error ?? hint}
        placeholderTextColor={colors.textMuted}
        style={[
          typography.body,
          {
            minHeight: MIN_TOUCH_TARGET,
            paddingHorizontal: spacing.md,
            borderWidth: 1,
            borderRadius: radius.md,
            borderColor: error ? colors.danger : colors.controlBorder,
            backgroundColor: colors.surface,
            color: colors.text,
          },
        ]}
        {...inputProps}
      />
      {error ? (
        <Text
          accessibilityLiveRegion="polite"
          style={[typography.caption, { color: colors.danger }]}
        >
          {error}
        </Text>
      ) : hint ? (
        <Text style={[typography.caption, { color: colors.textMuted }]}>{hint}</Text>
      ) : null}
    </View>
  );
}
