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
GitHub Actions are enabled for NAK-1010 CI after independent review with no findings.
GitHub reports `disabled_manually` for both `deploy.yml` and `release.yml`.
CI enablement does not authorize deployment or release.

NAK-1010 moves CI to fixed `ubuntu-24.04` standard GitHub-hosted runners.
Every CI job requires `github.event.repository.visibility == 'public'` before runner assignment.
The aggregate uses `always()` with the same public guard.
Private, internal, or missing visibility skips both jobs.
Paid, larger, custom, and dynamically selected runners are not allowed in this CI workflow.
Standard hosted runner usage is free for public repositories.
See [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Regular, Dependabot, and fork pull requests run `mise run verify` on fresh hosted VMs.
Pushes to `main` and manual `workflow_dispatch` canaries run the same gate.
The existing `trusted-verification` job identifier remains stable; it now verifies all pull request code.
Each verification job has read-only contents access, full Git history, and no persisted checkout credentials.
The workflow references no secrets, environments, deployment runners, or privileged pull request events.
A SHA-pinned Mise action installs Mise `2026.7.17` and the complete locked toolchain.
Tool caching is disabled. Tool versions and Linux x64 checksums come from `mise.toml` and `mise.lock`.

The stable `safe-fork-gate` check depends on code verification.
It fails for failed, cancelled, or skipped verification.
It runs one fixed shell check without checkout, repository code, or a token.
The dependency result enters through an environment variable, without expression interpolation in shell commands.
The previous metadata-only fork and Dependabot block is removed.
Fresh hosted VMs provide the CI isolation previously missing under NAK-902 and OPS-283.
Independent review accepted the CI boundary in commit `b40b2f08`.

Keep `deploy.yml` and `release.yml` manually disabled through GitHub workflow controls.
Preserve `KENGEN_DEPLOY_APPROVED` and all production environment and runner restrictions.
Confirm repository visibility is public and allow the pinned checkout and Mise actions.
Keep fork tokens read-only, secrets unavailable, and the required fork approval policy enabled.
[Canary 36105215480](https://github.com/NakamaDevs/kengen/actions/runs/36105215480) passed earlier CI and security gates on Ubuntu.
It failed dependency review with `License findings are missing.` before Go tests and lint.
Dependency review now downloads Go modules before scanning their licenses on fresh runners.
A successful full hosted verification remains required.
Require successful full verification and the aggregate before accepting the migration as operational.
Then confirm regular, Dependabot, and fork pull request checks under their actual event contexts.
A manual canary alone does not prove fork pull request behavior.
Keep `safe-fork-gate` as the required aggregate check.
This readiness record reflects verified Actions settings; it does not change workflows or repository settings.

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
