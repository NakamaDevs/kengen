import importlib.util
import os
import json
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("credentials", Path(__file__).with_name("credentials.py"))
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


class CredentialTests(unittest.TestCase):
    def test_backup_preserves_existing_note_fields(self):
        key = secrets.token_urlsafe(32)
        existing = {'title': credentials.BACKUP_ITEM, 'category': 'SECURE_NOTE',
                    'fields': [{'id': 'notesPlain', 'type': 'STRING', 'value': 'keep'}]}
        def execute(argv, **kwargs):
            from subprocess import CompletedProcess
            if argv[2] == 'list':
                return CompletedProcess(argv, 0, json.dumps([{'id': 'item-id', 'title': credentials.BACKUP_ITEM}]))
            if argv[2] == 'get':
                return CompletedProcess(argv, 0, json.dumps(existing))
            document = json.loads(Path(argv[argv.index('--template') + 1]).read_text())
            self.assertIn(existing['fields'][0], document['fields'])
            self.assertEqual(document['fields'][-1]['value'], key)
            return CompletedProcess(argv, 0, '')
        with patch.object(credentials.subprocess, 'run', side_effect=execute):
            credentials.backup(key)

    def test_cached_key_does_not_contact_onepassword(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mise.local.toml"
            key = secrets.token_urlsafe(32)
            credentials.cache(path, {"DOKPLOY_API_KEY": key})
            with patch.dict(os.environ, {}, clear=True), patch.object(credentials, "read_vault", side_effect=AssertionError):
                self.assertEqual(credentials.obtain(path), key)

    def test_missing_key_is_cached_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mise.local.toml"
            key = secrets.token_urlsafe(32)
            with patch.dict(os.environ, {}, clear=True), patch.object(credentials, "read_vault", return_value=key) as vault:
                self.assertEqual(credentials.obtain(path), key)
                self.assertEqual(credentials.obtain(path), key)
                vault.assert_called_once()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_preserve_other_mise_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mise.local.toml"
            path.write_text('[env]\nOTHER = "keep"\n\n[tasks.sample]\nrun = "true"\n')
            path.chmod(0o600)
            credentials.cache(path, {"DOKPLOY_API_KEY": secrets.token_urlsafe(32)})
            data = credentials.read_config(path)
            self.assertEqual(data['env']['OTHER'], 'keep')
            self.assertEqual(data['tasks']['sample']['run'], 'true')

    def test_environment_takes_precedence(self):
        key = secrets.token_urlsafe(32)
        with patch.dict(os.environ, {"DOKPLOY_API_KEY": key}), patch.object(credentials, "read_vault", side_effect=AssertionError):
            self.assertEqual(credentials.obtain(Path('/does/not/exist')), key)

    def test_ci_never_opens_onepassword(self):
        with patch.dict(os.environ, {"CI": "true"}, clear=True), patch.object(credentials, "read_vault", side_effect=AssertionError):
            with self.assertRaises(credentials.CredentialError):
                credentials.obtain(Path('/does/not/exist'))

    def test_reject_symlink_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.write_text('untouched')
            path = Path(folder) / 'mise.local.toml'
            path.symlink_to(target)
            with self.assertRaises(credentials.CredentialError):
                credentials.cache(path, {'DOKPLOY_API_KEY': secrets.token_urlsafe(32)})
            self.assertEqual(target.read_text(), 'untouched')
