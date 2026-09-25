#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow_file="${repository_root}/.github/workflows/safe-fork-gates.yml"
mise_file="${repository_root}/mise.toml"
gitleaks_file="${repository_root}/.gitleaks.toml"
gitleaks_ignore_file="${repository_root}/.gitleaksignore"

fail() {
  printf 'PR 3 security hardening validation failed: %s\n' "$1" >&2
  exit 1
}

bash "${repository_root}/scripts/validate-safe-fork-gates.sh"

grep -Fq 'regexTarget = "match"' "${gitleaks_file}" || fail "Gitleaks exception is not match-scoped"
grep -Fq '[[allowlists]]' "${gitleaks_file}" || fail "Gitleaks exceptions are not scoped"
! grep -Fq '[allowlist]' "${gitleaks_file}" || fail "Gitleaks legacy exception table is enabled"
grep -Fq 'useDefault = true' "${gitleaks_file}" || fail "Gitleaks default rules are disabled"
grep -Fq 'Q-52ee0e33-980f-4a19-9821-39530de9f304-0' "${gitleaks_file}" || fail "Gitleaks exception is not exact"
! grep -Fq 'commits = [' "${gitleaks_file}" || fail "historical Gitleaks exceptions use commit-only scope"
! grep -Fq 'paths = [' "${gitleaks_file}" || fail "historical Gitleaks exceptions use path-only scope"
[[ -f "${gitleaks_ignore_file}" ]] || fail "historical Gitleaks fingerprint allowlist is missing"
grep -Eq '^[0-9a-f]{40}:.+:[a-z0-9-]+:[0-9]+$' "${gitleaks_ignore_file}" || fail "historical Gitleaks fingerprints are not exact"
[[ "$(grep -Ec '^[0-9a-f]{40}:.+:[a-z0-9-]+:[0-9]+$' "${gitleaks_ignore_file}")" -eq 28 ]] || fail "historical Gitleaks fingerprint count changed"

grep -Fq '[settings]' "${mise_file}" || fail "Mise lock settings are missing"
grep -Fq 'locked = true' "${mise_file}" || fail "Mise locked mode is disabled"
[[ -f "${repository_root}/mise.lock" ]] || fail "Mise integrity lockfile is missing"
grep -Fq 'checksum = "sha256:' "${repository_root}/mise.lock" || fail "Mise lockfile has no checksums"
grep -Fq 'gitleaks git --config .gitleaks.toml --redact --no-banner' "${mise_file}" || fail "complete history secret scan is missing"
grep -Fq 'mise run scan:secrets:staged' "${mise_file}" || fail "staged secret scan is missing"
grep -Fq 'mise run test:secret-canary' "${mise_file}" || fail "secret canary is missing"
