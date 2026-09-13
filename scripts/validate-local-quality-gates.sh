#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mise_file="${repository_root}/mise.toml"

fail() {
  printf 'local quality gate validation failed: %s\n' "$1" >&2
  exit 1
}

grep -Fqx 'gitleaks = "8.30.0"' "${mise_file}" || fail "gitleaks is not pinned"
grep -Fqx 'trivy = "0.69.2"' "${mise_file}" || fail "trivy is not pinned"
[[ -f "${repository_root}/mise.lock" ]] || fail "Mise integrity lockfile is missing"
for locked_tool in actionlint gitleaks go trivy; do
  grep -Fq "[[tools.${locked_tool}]]" "${repository_root}/mise.lock" || fail "${locked_tool} is absent from the Mise lockfile"
done
grep -Fq 'checksum = "sha256:' "${repository_root}/mise.lock" || fail "Mise lockfile lacks checksums"
grep -Fq '[tasks."scan:secrets"]' "${mise_file}" || fail "secret scan task is missing"
[[ -f "${repository_root}/.gitleaks.toml" ]] || fail "secret scan allowlist is missing"
grep -Fq 'gitleaks git --config .gitleaks.toml --redact --no-banner' "${mise_file}" || fail "secret scan task changed"
grep -Fq '[tasks."review:dependencies"]' "${mise_file}" || fail "dependency and license review task is missing"
grep -Fq '/usr/bin/python3 -B scripts/review_dependencies.py' "${mise_file}" || fail "dependency and license review task changed"
grep -Fq '[tasks."check:upstream-compatibility"]' "${mise_file}" || fail "upstream compatibility task is missing"
grep -Fq 'bash scripts/validate-upstream-compatibility.sh' "${mise_file}" || fail "upstream compatibility task changed"
grep -Fq 'mise run scan:secrets' "${mise_file}" || fail "full gate omits secret scanning"
grep -Fq 'mise run review:dependencies' "${mise_file}" || fail "full gate omits dependency and license review"
grep -Fq 'mise run check:upstream-compatibility' "${mise_file}" || fail "full gate omits upstream compatibility"

grep -Fq 'mise run test:dependency-policy' "${mise_file}" || fail "dependency policy tests are missing"
