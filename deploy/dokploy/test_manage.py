"""Test source selection and credential handling without deployment access."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import manage


class ManageTests(unittest.TestCase):
    def test_build_context_uses_commit_instead_of_checkout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', '-C', folder, *args]).decode().strip()
            git('init', '-q')
            git('config', 'user.name', 'Deployment test')
            git('config', 'user.email', 'test@example.invalid')
            (root / 'source').write_text('release')
            git('add', 'source')
            git('commit', '-qm', 'release')
            commit = git('rev-parse', 'HEAD')
            (root / 'source').write_text('newer checkout')
            with patch.object(manage, 'ROOT', root), manage.build_context(commit) as context:
                self.assertEqual((context / 'source').read_text(), 'release')
                self.assertFalse((context / '.git').exists())

    def test_invalid_ssh_host_fails_before_any_transfer(self):
        args = argparse.Namespace(tag=None, image=None, status=False)
        with patch.dict(os.environ, {'KENGEN_SSH_HOST': '-oProxyCommand=bad'}), \
                patch.object(manage, 'source_commit', return_value='a' * 40), \
                patch.object(manage, 'run') as run:
            with self.assertRaises(manage.deploy.DeployError):
                manage.remote(args, 'test-only')
            run.assert_not_called()

    def test_child_processes_do_not_inherit_credentials(self):
        with patch.dict(os.environ, {'DOKPLOY_API_KEY': 'test-only', 'AWS_SESSION_TOKEN': 'test-only'}), \
                patch.object(manage.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'ok')) as run:
            manage.run(['true'])
            self.assertNotIn('DOKPLOY_API_KEY', run.call_args.kwargs['env'])
            self.assertNotIn('AWS_SESSION_TOKEN', run.call_args.kwargs['env'])
