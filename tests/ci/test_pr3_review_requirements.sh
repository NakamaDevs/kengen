#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow_file="${repository_root}/.github/workflows/safe-fork-gates.yml"

grep -Fq 'fetch-depth: 0' "${workflow_file}"
grep -Fq 'run: mise run verify' "${workflow_file}"
test -f "${repository_root}/.nakama/upstream-divergences.toml"
bash "${repository_root}/scripts/validate-upstream-compatibility.sh"
