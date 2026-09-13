#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mise_file="${repository_root}/mise.toml"
makefile="${repository_root}/Makefile"
lock_file="${repository_root}/mise.lock"

fail() {
  printf 'lint tool pin validation failed: %s\n' "$1" >&2
  exit 1
}

grep -Fqx 'golangci-lint = "2.13.2"' "${mise_file}" || fail "golangci-lint is not pinned"
grep -Fqx 'locked = true' "${mise_file}" || fail "Mise locked mode is disabled"
! grep -Fq 'golangci-lint@latest' "${makefile}" || fail "Makefile retains a mutable golangci-lint install"
grep -Fq 'mise exec golangci-lint@2.13.2 -- golangci-lint run' "${makefile}" || fail "Makefile does not use the pinned lint tool"
[[ -f "${lock_file}" ]] || fail "Mise integrity lockfile is missing"
grep -Fq '[[tools.golangci-lint]]' "${lock_file}" || fail "golangci-lint is absent from the lockfile"
grep -Fq 'checksum = "sha256:' "${lock_file}" || fail "Mise lockfile lacks checksums"
