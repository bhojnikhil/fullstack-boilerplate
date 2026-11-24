# ADR 0005: Security scans and shared pre-commit checks

Status: Accepted

Dependency review compares what a PR introduces. It cannot surface every newly
published advisory against versions already locked on the default branch.
Likewise, the pre-commit secret check only sees staged changes.

Run GitHub Dependency Review on PRs and independently audit the locked API and
production JS dependencies on PRs, main pushes, and a weekly schedule. Gitleaks
scans the PR commit range or the full fetched history, depending on the event.
Download its CLI by exact version and verify the release archive against a
pinned checksum. This uses the same scanner as the local hook and needs only
read access to the repository.

Run pre-commit locally and in CI against the same API and JS lockfiles used by
the normal lint and type-check commands. The security gates remain independently
visible when a new advisory affects an existing lockfile.
