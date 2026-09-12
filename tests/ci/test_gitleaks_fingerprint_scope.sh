#!/usr/bin/env bash
set -euo pipefail

fixture_directory="$(mktemp -d)"
trap 'rm -rf "${fixture_directory}"' EXIT

cd "${fixture_directory}"
git init --quiet
git config user.name 'Gitleaks scope test'
git config user.email 'gitleaks-scope-test@example.invalid'

cat > .gitleaks.toml <<'EOF'
[extend]
useDefault = true
EOF

canary_prefix='canary_secret_'
printf 'api_key = "%s%s"\napi_key = "%s%s"\n' \
  "${canary_prefix}" '123456789' \
  "${canary_prefix}" '987654321' > same-revision.txt
git add .gitleaks.toml same-revision.txt
git commit --quiet -m 'test: add synthetic secret findings'

if gitleaks git --config .gitleaks.toml --report-format json --report-path initial.json --redact --no-banner; then
  printf 'initial fingerprint scope fixture unexpectedly passed\n' >&2
  exit 1
fi

first_fingerprint="$(jq -r '.[0].Fingerprint' initial.json)"
[[ -n "${first_fingerprint}" && "${first_fingerprint}" != "null" ]] || {
  printf 'initial fingerprint is missing\n' >&2
  exit 1
}
printf '%s\n' "${first_fingerprint}" > .gitleaksignore

if gitleaks git --config .gitleaks.toml --report-format json --report-path scoped.json --redact --no-banner; then
  printf 'fingerprint scope fixture unexpectedly passed\n' >&2
  exit 1
fi

[[ "$(jq 'length' scoped.json)" -eq 1 ]] || {
  printf 'fingerprint scope hid more than one finding\n' >&2
  exit 1
}
[[ "$(jq -r '.[0].Fingerprint' scoped.json)" != "${first_fingerprint}" ]] || {
  printf 'fingerprint scope did not preserve the second finding\n' >&2
  exit 1
}
