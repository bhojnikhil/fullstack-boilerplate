import type { ReactNode } from "react";
import { View, type StyleProp, type ViewStyle } from "react-native";
import { useSafeAreaInsets, type Edge } from "react-native-safe-area-context";

import { useTheme } from "@/theme/use-theme";

interface ScreenProps {
  children: ReactNode;
  /**
   * Sides to pad with safe-area insets. Android is edge-to-edge, so content
   * draws under the status and navigation bars unless padded. Omit "top"
   * under a navigation header and "bottom" above a tab bar: those already
   * account for the insets.
   */
  edges?: readonly Edge[];
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

/**
 * Screen container. Uses the insets context (not the native SafeAreaView) so
 * that NetworkStatusBoundary can hand the top inset to the offline banner.
 */
export function Screen({
  children,
  edges = ["top", "bottom", "left", "right"],
  style,
  testID,
}: ScreenProps) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  return (
    <View
      testID={testID}
      style={[
        {
          flex: 1,
          backgroundColor: colors.background,
          paddingTop: edges.includes("top") ? insets.top : 0,
          paddingBottom: edges.includes("bottom") ? insets.bottom : 0,
          paddingLeft: edges.includes("left") ? insets.left : 0,
          paddingRight: edges.includes("right") ? insets.right : 0,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}
