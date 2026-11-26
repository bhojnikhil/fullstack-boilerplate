/** An error response from the API, in the `{error: {code, message, details}}` envelope. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The request never produced an HTTP response (offline, DNS, timeout, reset). */
export function isNetworkError(error: unknown): boolean {
  return (
    error instanceof TypeError ||
    (error instanceof Error && error.name === "AbortError")
  );
}

function fromEnvelope(status: number, body: unknown): ApiError {
  let code = "http_error";
  let message = `Request failed (${status})`;
  let details: Record<string, unknown> = {};
  const envelope = (body as { error?: Record<string, unknown> } | null | undefined)
    ?.error;
  if (envelope && typeof envelope === "object") {
    if (typeof envelope.code === "string") code = envelope.code;
    if (typeof envelope.message === "string") message = envelope.message;
    if (envelope.details && typeof envelope.details === "object") {
      details = envelope.details as Record<string, unknown>;
    }
  }
  return new ApiError(status, code, message, details);
}

/** Builds an ApiError from a response whose body has not been read yet. */
export async function readApiError(response: Response): Promise<ApiError> {
  try {
    return fromEnvelope(response.status, await response.clone().json());
  } catch {
    // Not JSON (a proxy error page, say): keep the generic message.
    return fromEnvelope(response.status, null);
  }
}

/**
 * Builds an ApiError from an openapi-fetch result. openapi-fetch has already
 * consumed the body of an error response and hands it over parsed as `error`,
 * so reading the response again would find nothing.
 */
export function apiErrorFromResult(result: {
  error?: unknown;
  response: Response;
}): ApiError {
  return fromEnvelope(result.response.status, result.error);
}

interface ClientResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Unwraps an openapi-fetch result: the data, or a thrown ApiError. */
export async function unwrap<T>(result: Promise<ClientResult<T>>): Promise<T> {
  const settled = await result;
  if (!settled.response.ok || settled.error !== undefined)
    throw apiErrorFromResult(settled);
  return settled.data as T;
}

/** Text safe to show a person: never raw server internals for unexpected failures. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return "Too many attempts. Wait a moment and try again.";
    if (error.status >= 500) return "The server had a problem. Try again shortly.";
    return error.message;
  }
  if (isNetworkError(error)) return "You appear to be offline. Check your connection.";
  return "Something went wrong. Try again.";
}
