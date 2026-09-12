#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "${repository_root}/scripts/validate-pr3-security-hardening.sh"
bash "${repository_root}/tests/ci/test_gitleaks_fingerprint_scope.sh"
bash "${repository_root}/tests/ci/test_secret_scan_canary.sh"
