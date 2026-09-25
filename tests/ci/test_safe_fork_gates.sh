#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow_file="${repository_root}/.github/workflows/safe-fork-gates.yml"
# Both jobs must use standard hosted runners, including the aggregate.
[[ "$(grep -Fc '    runs-on: ubuntu-24.04' "${workflow_file}")" -eq 2 ]]
grep -Fqx "    if: always() && github.event.repository.visibility == 'public'" "${workflow_file}"
"${repository_root}/scripts/validate-safe-fork-gates.sh"

if SAFE_FORK_GATES_WORKFLOW_FILE="${repository_root}/tests/ci/fixtures/untrusted-metadata-blank-line.yml" \
  "${repository_root}/scripts/validate-safe-fork-gates.sh"; then
  printf 'safe fork validator accepted an untrusted blank-line escape fixture\n' >&2
  exit 1
fi

# Mutate the real workflow so failures exercise one boundary at a time.
/usr/bin/python3 -B - "${repository_root}" <<'PYTEST'
from pathlib import Path
import os
import subprocess
import textwrap
import sys
import tempfile

root = Path(sys.argv[1])
source = (root / ".github/workflows/safe-fork-gates.yml").read_text()
validator = root / "scripts/validate-safe-fork-gates.sh"
# Execute the actual aggregate shell body without checkout, tokens, or network.
aggregate = source.split("  safe-fork-gate:\n", 1)[1]
assert "        run: |\n" in aggregate, "aggregate must use a fixed shell check"
script = textwrap.dedent(aggregate.split("        run: |\n", 1)[1])
with tempfile.TemporaryDirectory() as temporary:
    marker = Path(temporary) / "injected"
    outcomes = ("success", "failure", "cancelled", "skipped", "", f"$(touch {marker})")
    for outcome in outcomes:
        result = subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
                                cwd=temporary, capture_output=True, text=True,
                                env={"PATH": os.defpath, "VERIFICATION_RESULT": outcome})
        assert (result.returncode == 0) == (outcome == "success"), (outcome, result)
    assert not marker.exists(), "aggregate executed result text as shell code"
print("Aggregate passed six result cases, including injection rejection")

cases = []
for job in ("trusted-verification", "safe-fork-gate"):
    start = source.index(f"  {job}:\n")
    for runner in ("ubuntu-latest", "ubuntu-24.04-8core", "macos-latest-large",
                   "nakama-linux-x64", "[self-hosted, linux]", "${{ vars.CI_RUNNER }}",
                   "\n      group: paid-runners\n      labels: ubuntu-24.04"):
        changed = source[:start] + source[start:].replace("runs-on: ubuntu-24.04", f"runs-on: {runner}", 1)
        cases.append((f"{job} runner {runner}", changed, "must use only ubuntu-24.04"))
    guard = "github.event.repository.visibility == 'public'"
    for replacement in ("true", "github.event.repository.visibility != 'private'",
                        "github.event.repository.private == false", guard + " || true"):
        changed = source[:start] + source[start:].replace(guard, replacement, 1)
        cases.append((f"{job} visibility {replacement}", changed, "lacks its public job guard"))
for old, new, error in (
    ("always() && ", "", "lacks its public job guard"),
    ("  workflow_dispatch:\n", "", "unexpected workflow event or job"),
    ("contents: read", "contents: write", "privileged boundary"),
    ("persist-credentials: false", "persist-credentials: true", "checkout retains credentials"),
    ("install_args: --locked", "install_args: go", "tool installation is not locked"),
    ("version: 2026.7.17", "version: latest", "Mise version is not pinned"),
    ("cache: false", "cache: true", "shared tool cache is enabled"),
    ('"${VERIFICATION_RESULT}" != "success"', '"${VERIFICATION_RESULT}" == "failure"', "fixed result shell check"),
    ("shell: bash", "uses: actions/github-script@ed597411d8f924073f98dfc5c65a23a2325f34cd", "fixed result shell check"),
    ('"${VERIFICATION_RESULT}" != "success"', '"${{ needs.trusted-verification.result }}" != "success"', "fixed result shell check"),
    ("run: mise run verify", "run: echo '${{ secrets.CI_SECRET }}'", "privileged boundary"),
):
    cases.append((old, source.replace(old, new), error))
with tempfile.TemporaryDirectory() as temporary:
    workflow = Path(temporary) / "workflow.yml"
    for name, changed, error in cases:
        assert changed != source, name
        workflow.write_text(changed)
        result = subprocess.run(["bash", str(validator)], capture_output=True, text=True,
                                env={**os.environ, "SAFE_FORK_GATES_WORKFLOW_FILE": str(workflow)})
        assert result.returncode != 0 and error in result.stderr, (name, result.stdout, result.stderr)
print(f"Rejected {len(cases)} unsafe CI workflow mutations")
PYTEST
