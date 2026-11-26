const KEY = "pending_workspace_invitation";
export function savePendingInvite(token: string) {
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    /* Storage can be unavailable. */
  }
}
export function pendingInvite() {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}
export function clearPendingInvite() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* Storage can be unavailable. */
  }
}
