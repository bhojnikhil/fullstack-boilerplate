/** An invitation token opened while signed out; resumed after sign-in. In memory only. */
let pending: string | null = null;

export const peekPendingInvite = () => pending;
export const setPendingInvite = (token: string) => {
  pending = token;
};
export const clearPendingInvite = () => {
  pending = null;
};
