# Fork CI boundary

Kengen is a NakamaDevs fork of `openfga/openfga`.
The upstream workflows are stored in `.github/upstream-workflows-disabled`.
GitHub Actions ignores this directory.

The active workflow directory contains `safe-fork-gates.yml`, `release.yml`, and
`deploy.yml`. The release caller uses the deployment workflow from `main`.
Deployment also requires `KENGEN_DEPLOY_APPROVED=true` and the protected
`kengen-production` environment. The dedicated `nakama-kengen-deploy` group
must allow only this repository and
`NakamaDevs/kengen/.github/workflows/deploy.yml@refs/heads/main`.
Its registration uses the existing `hdbmm` macOS ARM64 host and OrbStack.
See [the deployment runbook](deploy/dokploy.md) for activation and rollback.
Repository administrators must keep Actions disabled until they approve this boundary.
NAK-902 does not enable Actions or change runner groups.

Same-repository pull requests run `mise run verify` on `nakama-linux-x64`.
The job guard checks the pull request head repository before runner assignment.
The job has read-only contents access.
Pushes to `main` use the same trusted verification after a merge.

Fork pull requests use `nakama-untrusted-metadata-linux-x64`.
That job has no token permissions, checkout, command, secret, or local action.
It uses one SHA-pinned GitHub-maintained metadata action with an empty token.
It only records GitHub pull request metadata.

Dependabot pull requests use the same metadata-only path.
The aggregate check fails after metadata handling for Dependabot and external forks.
OPS-283 must add an approved disposable Linux code runner before either can pass.

The stable `safe-fork-gate` check depends on both event jobs.
It completes after trusted verification for internal pull requests and pushes.
It completes after metadata handling for fork pull requests.

Keep every GitHub Action pinned to a full commit SHA.
Pin local tools to exact versions in `mise.toml`.
Run `mise run test:ci-gates` after any workflow edit.
Run `mise run test:local-quality-gates` after any local quality gate edit.
The full gate scans secrets, reviews dependency vulnerabilities and licenses, and checks upstream compatibility.
`.gitleaks.toml` excludes one exact static Grafana panel identifier.
Historical exceptions use immutable Gitleaks fingerprints. Each record includes the exact commit, path, rule, and line.
The secret gate scans complete reachable history and staged changes.
`mise.lock` supplies tool checksums, and Mise locked mode enforces the lockfile.
`.nakama/upstream-divergences.toml` attributes each reviewed path to one Linear issue.
Add one issue-approved path before a fork change modifies upstream-compatible code.

To import an upstream workflow, place it in the quarantine directory first.
Review its permissions, events, actions, and runner requirements.
Create a separate NakamaDevs workflow only after security review.
