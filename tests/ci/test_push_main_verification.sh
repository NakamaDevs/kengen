#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow_file="${repository_root}/.github/workflows/safe-fork-gates.yml"

grep -Fq 'push:' "${workflow_file}"
grep -Fq 'branches: [main]' "${workflow_file}"
grep -Fq "if: github.event_name == 'push' ||" "${workflow_file}"
grep -Fq 'needs: [trusted-verification, untrusted-metadata]' "${workflow_file}"
