# 0012: OpenAPI TypeScript client

## Decision

Use openapi-typescript and openapi-fetch for a generated contract and a small framework-independent fetch transport. Applications own token storage and refresh policy. Regenerate with `make gen-client`; CI checks for drift.

## Alternatives

Orval can generate TanStack Query hooks, but would couple the generated API surface to a query framework. A handwritten client would duplicate the API contract and drift more easily.

## Consequences

Web uses typed requests without generated hooks; applications must build their own query integration. The transport requires Fetch and a secure random number generator or explicit ID generators. A Jest import smoke test exists for mobile, but Metro bundling and runtime integration have not been verified.
