import { useCallback, useState } from "react";

import { describeError } from "@/lib/api-error";

/** Runs an async form action, tracking pending state and a readable error. */
export function useSubmit<Args extends unknown[]>(
  action: (...args: Args) => Promise<void>,
  describe: (error: unknown) => string = describeError,
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(
    async (...args: Args): Promise<boolean> => {
      if (pending) return false;
      setPending(true);
      setError(null);
      try {
        await action(...args);
        return true;
      } catch (caught) {
        setError(describe(caught));
        return false;
      } finally {
        setPending(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [action, pending],
  );
  return { run, pending, error, clearError: () => setError(null) };
}
