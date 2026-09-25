#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest_file="${repository_root}/.nakama/upstream-divergences.toml"

grep -Fq 'path = ".github/workflows/safe-fork-gates.yml"' "${manifest_file}"
grep -Fq 'issue = "NAK-902"' "${manifest_file}"
grep -Fq 'path = "go.mod"' "${manifest_file}"
grep -Fq 'path = "go.sum"' "${manifest_file}"
grep -Fq 'issue = "NAK-909"' "${manifest_file}"

# Each migration path must carry this issue, not an unrelated manifest entry.
for path in \
  .github/workflows/safe-fork-gates.yml \
  .nakama/upstream-divergences.toml \
  docs/fork-ci.md \
  scripts/validate-safe-fork-gates.sh \
  scripts/validate-pr3-security-hardening.sh \
  tests/ci/fixtures/untrusted-metadata-blank-line.yml \
  tests/ci/test_safe_fork_gates.sh \
  tests/ci/test_push_main_verification.sh \
  tests/ci/test_divergence_manifest_attribution.sh; do
  awk -v expected="${path}" '
    /^path = / { path = $0 }
    /^issue = / && path == "path = \"" expected "\"" {
      if ($0 == "issue = \"NAK-1010\"") found = 1
    }
    END { exit !found }
  ' "${manifest_file}"
done
