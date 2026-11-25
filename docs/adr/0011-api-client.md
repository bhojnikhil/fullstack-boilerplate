# 0011: OpenAPI TypeScript client

Use openapi-typescript and openapi-fetch. The generated contract types and small fetch-based runtime work without framework-specific hooks in both web and React Native; applications can choose their own query integration. The shared transport provides headers, idempotency and session-bound refresh, while applications own token storage and refresh policy. Regenerate with `make gen-client`; CI checks for drift.
