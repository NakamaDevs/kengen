"""Release routing must keep fork code away from the persistent Mac."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WorkflowTests(unittest.TestCase):
    def test_only_reviewed_workflows_are_active(self):
        self.assertEqual({p.name for p in (ROOT / '.github/workflows').iterdir()},
                         {'safe-fork-gates.yml', 'deploy.yml', 'release.yml'})

    def test_deployment_uses_restricted_macos_group_and_main(self):
        text = (ROOT / '.github/workflows/deploy.yml').read_text()
        for required in ['group: nakama-kengen-deploy',
                         'labels: [self-hosted, macOS, ARM64, host-hdbmm]',
                         "github.repository == 'NakamaDevs/kengen'",
                         "vars.KENGEN_DEPLOY_APPROVED == 'true'",
                         'environment: kengen-production', 'ref: main',
                         'fetch-depth: 0', 'persist-credentials: false',
                         'cancel-in-progress: false', 'permissions: {}',
                         '--check-ref --tag "$RELEASE_TAG"',
                         'KENGEN_DOKPLOY_COMPOSE_ID:', 'DOKPLOY_URL: http://localhost:3000']:
            self.assertIn(required, text)
        for blocked in ['pull_request:', 'pull_request_target:', 'ubuntu-latest',
                        'macos-latest', 'secrets: inherit', 'ref: ${{ inputs.tag }}']:
            self.assertNotIn(blocked, text)
        self.assertLess(text.index('--check-ref'), text.index('secrets.DOKPLOY_API_KEY', text.index('jobs:')))
        for action in re.findall(r'uses: (.+)', text):
            self.assertRegex(action, r'@[0-9a-f]{40}$')

    def test_release_calls_only_main_deployment_workflow(self):
        text = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('types: [published]', text)
        self.assertIn('uses: NakamaDevs/kengen/.github/workflows/deploy.yml@main', text)
        self.assertIn("github.repository == 'NakamaDevs/kengen'", text)
        self.assertIn('!github.event.release.prerelease', text)
        self.assertNotIn('runs-on:', text)
        self.assertNotIn('run:', text)
        self.assertNotIn('secrets: inherit', text)


if __name__ == '__main__':
    unittest.main()
