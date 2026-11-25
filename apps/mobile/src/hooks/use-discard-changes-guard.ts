import { usePreventRemove } from "expo-router";
import { Alert } from "react-native";

/**
 * Asks before leaving a screen with unsaved input. Covers every way of
 * leaving: the Android hardware/gesture back button, the header back button
 * and the iOS swipe-back gesture (react-navigation's usePreventRemove).
 *
 * `discard` must clear the unsaved state, so that `hasUnsavedChanges` becomes
 * false before the blocked navigation is repeated; otherwise the guard would
 * block it again.
 */
export function useDiscardChangesGuard(
  hasUnsavedChanges: boolean,
  discard: () => void,
): void {
  usePreventRemove(hasUnsavedChanges, ({ repeat }) => {
    Alert.alert("Discard changes?", "What you entered on this screen will be lost.", [
      { text: "Keep editing", style: "cancel" },
      {
        text: "Discard",
        style: "destructive",
        onPress: () => {
          discard();
          repeat();
        },
      },
    ]);
  });
}
