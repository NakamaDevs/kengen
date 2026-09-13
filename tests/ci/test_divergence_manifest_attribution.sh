#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest_file="${repository_root}/.nakama/upstream-divergences.toml"

grep -Fq 'path = ".github/workflows/safe-fork-gates.yml"' "${manifest_file}"
grep -Fq 'issue = "NAK-902"' "${manifest_file}"
grep -Fq 'path = "go.mod"' "${manifest_file}"
grep -Fq 'path = "go.sum"' "${manifest_file}"
grep -Fq 'issue = "NAK-909"' "${manifest_file}"
