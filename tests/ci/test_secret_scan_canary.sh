#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fixture_directory="$(mktemp -d)"
trap 'rm -rf "${fixture_directory}"' EXIT

canary_prefix='canary_secret_'
canary_suffix='123456789'
printf 'api_key = "%s%s"\n' "${canary_prefix}" "${canary_suffix}" > "${fixture_directory}/canary.txt"

if gitleaks detect --source "${fixture_directory}" --no-git --config "${repository_root}/.gitleaks.toml" --redact --no-banner; then
  printf 'secret scan canary unexpectedly passed\n' >&2
  exit 1
fi
