#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest_file="${repository_root}/.nakama/upstream-divergences.toml"
cd "${repository_root}"

fail() {
  printf 'upstream compatibility validation failed: %s\n' "$1" >&2
  exit 1
}

grep -Fqx 'module github.com/openfga/openfga' go.mod || fail "Go module path changed"
grep -Fq 'Apache License' LICENSE || fail "Apache-2.0 license is missing"
[[ -f "${manifest_file}" ]] || fail "reviewed divergence manifest is missing"
mapfile -t approved_paths < <(
  awk -F ' = ' '
    /^\[\[approved_path\]\]$/ { path = ""; issue = "" }
    $1 == "path" { gsub(/"/, "", $2); path = $2 }
    $1 == "issue" {
      gsub(/"/, "", $2)
      issue = $2
      if (path != "" && issue ~ /^NAK-[0-9]+$/) print path
    }
  ' "${manifest_file}"
)
[[ "${#approved_paths[@]}" -gt 0 ]] || fail "divergence manifest has no attributed approved paths"

unexpected_files=""
while IFS= read -r changed_file; do
  approved=false
  for approved_path in "${approved_paths[@]}"; do
    [[ "${changed_file}" == "${approved_path}" ]] && approved=true && break
  done
  ${approved} || unexpected_files+="${changed_file}"$'\n'
done < <(git diff --name-only origin/main...HEAD)

[[ -z "${unexpected_files}" ]] || fail "integration change modifies upstream files: ${unexpected_files}"
