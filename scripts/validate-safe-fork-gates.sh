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
while IFS= read -r candidate; do
  case "$(basename "${candidate}")" in
    safe-fork-gates.yml|deploy.yml|release.yml) ;;
    *) fail "active workflow directory contains an unreviewed workflow" ;;
  esac
done < <(find "${workflow_directory}" -maxdepth 1 -type f)
/usr/bin/python3 -B -m unittest discover -s "${repository_root}/deploy/dokploy" -p 'test_workflows.py'

# Keep this contract deliberately strict for this small, reviewed workflow.
# Scope each assertion to its job so another job cannot satisfy a missing guard.
job_body() {
  awk -v job="$1" '
    $0 == "  " job ":" { found = 1; next }
    found && /^  [[:alnum:]_-]+:$/ { exit }
    found { print }
  ' "${workflow_file}"
}
[[ "$(grep -Ec '^  [[:alnum:]_-]+:$' "${workflow_file}")" -eq 5 ]] || fail "unexpected workflow event or job"
grep -Fqx '  pull_request:' "${workflow_file}" || fail "pull request event is missing"
grep -Fqx '  workflow_dispatch:' "${workflow_file}" || fail "manual canary event is missing"
grep -Fqx '  push:' "${workflow_file}" || fail "push event is missing"
grep -Fqx '    branches: [main]' "${workflow_file}" || fail "push does not target main"
grep -Fqx 'permissions: {}' "${workflow_file}" || fail "default token permissions are not empty"
! grep -Eq '(secrets\.|pull_request_target|workflow_run|^[[:space:]]*(environment|container|services):|uses: \./|write)' "${workflow_file}" || fail "workflow exposes a privileged boundary"

verification_job="$(job_body trusted-verification)"
aggregate_job="$(job_body safe-fork-gate)"
for job in trusted-verification safe-fork-gate; do
  body="$(job_body "${job}")"
  [[ "$(grep -Ec '^[[:space:]]*runs-on:' <<<"${body}")" -eq 1 ]] &&
    grep -Fqx '    runs-on: ubuntu-24.04' <<<"${body}" || fail "${job} must use only ubuntu-24.04"
  [[ "$(grep -Ec '^[[:space:]]*if:' <<<"${body}")" -eq 1 ]] || fail "${job} must have one public job guard"
  guard="github.event.repository.visibility == 'public'"
  [[ "${job}" != safe-fork-gate ]] || guard="always() && ${guard}"
  grep -Fqx "    if: ${guard}" <<<"${body}" || fail "${job} lacks its public job guard"
done

grep -Fqx '    permissions:' <<<"${verification_job}" || fail "verification permissions are missing"
grep -Fqx '      contents: read' <<<"${verification_job}" || fail "verification lacks read-only contents"
grep -Fq 'uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683' <<<"${verification_job}" || fail "checkout is not pinned"
grep -Fqx '          fetch-depth: 0' <<<"${verification_job}" || fail "checkout lacks full history"
grep -Fqx '          persist-credentials: false' <<<"${verification_job}" || fail "checkout retains credentials"
grep -Fq 'uses: jdx/mise-action@7e36c90d9ab29c415a2384db3006f3ec8a8cc654' <<<"${verification_job}" || fail "Mise action is not pinned"
grep -Fqx '          version: 2026.7.17' <<<"${verification_job}" || fail "Mise version is not pinned"
grep -Fqx '          install_args: --locked' <<<"${verification_job}" || fail "tool installation is not locked"
grep -Fqx '          cache: false' <<<"${verification_job}" || fail "shared tool cache is enabled"
grep -Fqx '        run: mise run verify' <<<"${verification_job}" || fail "verification lacks the full local gate"

grep -Fqx '    permissions: {}' <<<"${aggregate_job}" || fail "aggregate token permissions are not empty"
grep -Fqx '    needs: [trusted-verification]' <<<"${aggregate_job}" || fail "aggregate lacks code verification"
# Compare the complete step body: no checkout, action, extra command, or interpolation in shell.
expected_steps="$(cat <<'STEPS'
      - name: Record safe gate result
        shell: bash
        env:
          VERIFICATION_RESULT: ${{ needs.trusted-verification.result }}
        run: |
          if [[ "${VERIFICATION_RESULT}" != "success" ]]; then
            printf 'Code verification result is %s\n' "${VERIFICATION_RESULT}" >&2
            exit 1
          fi
          printf 'Code verification completed successfully\n'
STEPS
)"
actual_steps="$(sed -n '/^    steps:$/,$p' <<<"${aggregate_job}" | tail -n +2)"
[[ "${actual_steps}" == "${expected_steps}" ]] || fail "aggregate must use only the fixed result shell check"

while IFS= read -r action; do
  [[ "${action}" =~ @[0-9a-f]{40}$ ]] || fail "workflow action is not pinned to a full commit SHA"
done < <(grep -E '^[[:space:]]*uses:' "${workflow_file}")
