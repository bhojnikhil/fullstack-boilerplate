import { useNavigation, usePreventRemove } from "expo-router";
import { Alert } from "react-native";

/**
 * Asks before leaving a screen with unsaved input. Covers every way of
 * leaving: the Android hardware/gesture back button, the header back button
 * and the iOS swipe-back gesture (react-navigation's usePreventRemove).
 */
export function useDiscardChangesGuard(hasUnsavedChanges: boolean): void {
  const navigation = useNavigation();
  usePreventRemove(hasUnsavedChanges, ({ data }) => {
    Alert.alert("Discard changes?", "What you entered on this screen will be lost.", [
      { text: "Keep editing", style: "cancel" },
      {
        text: "Discard",
        style: "destructive",
        onPress: () => navigation.dispatch(data.action),
      },
    ]);
  });
}
