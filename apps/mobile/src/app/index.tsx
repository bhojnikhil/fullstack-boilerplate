import { Redirect } from "expo-router";

// No session handling yet (phase 9b adds auth and a guard that picks between
// the (auth) and (app) groups), so the app always starts at sign-in.
export default function Index() {
  return <Redirect href="/sign-in" />;
}
