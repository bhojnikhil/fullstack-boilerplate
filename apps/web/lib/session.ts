export class SessionChangedError extends Error {
  constructor() {
    super("Signed in as a different session in another tab; the request was not sent.");
    this.name = "SessionChangedError";
  }
}
