#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
"${repository_root}/scripts/validate-safe-fork-gates.sh"

if SAFE_FORK_GATES_WORKFLOW_FILE="${repository_root}/tests/ci/fixtures/untrusted-metadata-blank-line.yml" \
  "${repository_root}/scripts/validate-safe-fork-gates.sh"; then
  printf 'safe fork validator accepted an untrusted blank-line escape fixture\n' >&2
  exit 1
fi
