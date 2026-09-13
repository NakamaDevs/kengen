#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow_directory="${repository_root}/.github/workflows"
workflow_file="${SAFE_FORK_GATES_WORKFLOW_FILE:-${workflow_directory}/safe-fork-gates.yml}"

fail() {
  printf 'safe fork gate validation failed: %s\n' "$1" >&2
  exit 1
}

[[ -f "${workflow_file}" ]] || fail "missing trusted workflow"
[[ -d "${repository_root}/.github/upstream-workflows-disabled" ]] || fail "missing upstream workflow quarantine"
[[ "$(find "${workflow_directory}" -maxdepth 1 -type f | wc -l | tr -d ' ')" == "1" ]] || fail "active workflow directory contains inherited workflows"

grep -Fqx 'permissions: {}' "${workflow_file}" || fail "default token permissions are not empty"
grep -Fq "if: github.event_name == 'push' || (github.event.pull_request.head.repo.full_name == github.repository && github.event.pull_request.user.login != 'dependabot[bot]')" "${workflow_file}" || fail "trusted job lacks same-repository guard"
grep -Fq 'runs-on: nakama-linux-x64' "${workflow_file}" || fail "trusted job lacks the trusted runner label"
grep -Fq 'uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683' "${workflow_file}" || fail "checkout is not pinned to a full commit SHA"
grep -Fq 'fetch-depth: 0' "${workflow_file}" || fail "trusted checkout lacks full history"
grep -Fq 'persist-credentials: false' "${workflow_file}" || fail "trusted checkout retains credentials"
grep -Fq 'run: mise run verify' "${workflow_file}" || fail "trusted job lacks the full local gate"
grep -Fq 'runs-on: nakama-untrusted-metadata-linux-x64' "${workflow_file}" || fail "untrusted metadata job lacks its isolated runner"
grep -Fq "if: github.event_name == 'pull_request' && (github.event.pull_request.user.login == 'dependabot[bot]' || github.event.pull_request.head.repo.full_name != github.repository)" "${workflow_file}" || fail "untrusted metadata job lacks its blocked pull request guard"
grep -Fq 'uses: actions/github-script@ed597411d8f924073f98dfc5c65a23a2325f34cd' "${workflow_file}" || fail "untrusted metadata action is not pinned to a full commit SHA"
grep -Fq 'github-token: ""' "${workflow_file}" || fail "untrusted metadata job can access a token"
grep -Fq 'safe-fork-gate:' "${workflow_file}" || fail "stable aggregate gate is missing"
grep -Fq 'needs: [trusted-verification, untrusted-metadata]' "${workflow_file}" || fail "aggregate gate lacks both event jobs"

untrusted_job="$(awk '
  /^  untrusted-metadata:$/ { in_untrusted_job = 1; next }
  in_untrusted_job && /^  [[:alnum:]_-]+:$/ { exit }
  in_untrusted_job { print }
' "${workflow_file}")"
! grep -Eq '(actions/checkout|^[[:space:]]*run:|secrets\.|uses: \./)' <<<"${untrusted_job}" || fail "untrusted metadata job can execute repository code"

while IFS= read -r action; do
  [[ "${action}" =~ @[0-9a-f]{40}$ ]] || fail "workflow action is not pinned to a full commit SHA"
done < <(grep -E '^[[:space:]]*uses:' "${workflow_file}")
