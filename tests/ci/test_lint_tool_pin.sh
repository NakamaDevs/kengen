#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "${repository_root}/scripts/validate-lint-tool-pin.sh"
