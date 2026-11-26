import Constants from "expo-constants";

/**
 * Native Google sign-in needs a development or production build: the native
 * module does not exist in Expo Go. The module is loaded lazily so the rest of
 * the app (and Expo Go) keeps working without it.
 */
interface GoogleModule {
  GoogleSignin: {
    configure(options: { webClientId: string; iosClientId?: string }): void;
    hasPlayServices(options?: {
      showPlayServicesUpdateDialog?: boolean;
    }): Promise<boolean>;
    signIn(): Promise<{ type: string; data?: { idToken?: string | null } }>;
    signOut(): Promise<unknown>;
  };
  statusCodes: Record<string, string>;
}

function loadModule(): GoogleModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("@react-native-google-signin/google-signin") as GoogleModule;
  } catch {
    return null;
  }
}

export function googleClientIds(): { web: string; ios?: string } | null {
  const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;
  const web = extra.googleWebClientId;
  const ios = extra.googleIosClientId;
  if (typeof web !== "string" || !web) return null;
  return { web, ...(typeof ios === "string" && ios ? { ios } : {}) };
}

export function isGoogleSignInAvailable(): boolean {
  return googleClientIds() !== null && loadModule() !== null;
}

export class GoogleCancelled extends Error {
  constructor() {
    super("Google sign-in was cancelled");
    this.name = "GoogleCancelled";
  }
}

/** Opens the native Google account chooser and returns a Google ID token. */
export async function getGoogleIdToken(): Promise<string> {
  const ids = googleClientIds();
  const module = loadModule();
  if (!ids || !module)
    throw new Error("Google sign-in is not available in this build.");
  const { GoogleSignin, statusCodes } = module;
  // The web client id is the ID token's audience; the API verifies it.
  GoogleSignin.configure({
    webClientId: ids.web,
    ...(ids.ios ? { iosClientId: ids.ios } : {}),
  });
  try {
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const response = await GoogleSignin.signIn();
    if (response.type !== "success" || !response.data?.idToken)
      throw new GoogleCancelled();
    return response.data.idToken;
  } catch (error) {
    if ((error as { code?: string }).code === statusCodes.SIGN_IN_CANCELLED) {
      throw new GoogleCancelled();
    }
    throw error;
  }
}

/** Forget the Google account on this device so the next sign-in shows the chooser. */
export async function googleSignOutQuietly(): Promise<void> {
  try {
    await loadModule()?.GoogleSignin.signOut();
  } catch {
    // Not signed in with Google, or the module is unavailable.
  }
}
