"""Cache the Dokploy credential locally. This is not an AWS credential provider."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = "op://prj_nakamadevs_homelab/Dokploy - hdbmm/API key"
VAULT = 'prj_nakamadevs_homelab'
BACKUP_ITEM = 'Kengen deploy credential'


class CredentialError(Exception):
    pass


def read_config(path):
    if path.is_symlink():
        raise CredentialError("The local credential file must not be a symlink.")
    if not path.exists():
        return {}
    if path.stat().st_mode & 0o077:
        raise CredentialError("Set mode 0600 on mise.local.toml before using cached credentials.")
    try:
        return tomllib.loads(path.read_text())
    except (OSError, ValueError):
        raise CredentialError("Cannot read mise.local.toml.") from None


def cache(path, values):
    data = read_config(path)
    env = data.get('env', {})
    if not isinstance(env, dict):
        raise CredentialError("mise.local.toml must use an [env] table.")
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    output, inside, found = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('['):
            inside = stripped == '[env]'
            if inside:
                found = True
                output.append(line)
                output.extend(f'{k} = {json.dumps(v)}\n' for k, v in values.items())
                continue
        matched = next((k for k in values if re.match(
            r'\s*(?:' + re.escape(k) + r'|"' + re.escape(k) + r'")\s*=', line)), None) if inside else None
        if matched:
            if not isinstance(env.get(matched), str):
                raise CredentialError("Cannot replace a structured mise credential setting.")
            continue
        output.append(line)
    if not found:
        output.append('\n[env]\n')
        output.extend(f'{k} = {json.dumps(v)}\n' for k, v in values.items())
    result = ''.join(output)
    try:
        parsed = tomllib.loads(result)
        if any(parsed['env'][k] != v for k, v in values.items()):
            raise ValueError
    except (ValueError, KeyError):
        raise CredentialError("Cannot safely update the local mise configuration.") from None
    fd, temporary = tempfile.mkstemp(prefix='.kengen-cache-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(result)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_vault():
    for reference in (f'op://{VAULT}/{BACKUP_ITEM}/DOKPLOY_API_KEY', REFERENCE):
        try:
            result = subprocess.run(['op', 'read', reference], capture_output=True, text=True, timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.stdout.strip():
            return result.stdout.strip()
    raise CredentialError("Dokploy key is missing locally. Enable 1Password Settings > Developer > Integrate with 1Password CLI, then run deploy:credentials once; or use deploy:credentials -- --prompt.")


def obtain(path=ROOT / 'mise.local.toml'):
    key = os.environ.get('DOKPLOY_API_KEY', '').strip()
    if key:
        return key
    key = read_config(path).get('env', {}).get('DOKPLOY_API_KEY', '')
    if isinstance(key, str) and key.strip():
        return key
    if os.environ.get('CI'):
        raise CredentialError("DOKPLOY_API_KEY is missing from the CI secret or local cache.")
    key = read_vault()
    cache(path, {'DOKPLOY_API_KEY': key})
    return key


def backup(key):
    """Explicit one-time backup. Normal deployments never call this function."""
    try:
        result = subprocess.run(['op', 'item', 'list', '--vault', VAULT, '--format=json'],
                                capture_output=True, text=True, check=True, timeout=30)
        matches = [item for item in json.loads(result.stdout) if item['title'] == BACKUP_ITEM]
        if len(matches) > 1:
            raise CredentialError('More than one Kengen deploy credential item exists in 1Password.')
        item = {'title': BACKUP_ITEM, 'category': 'SECURE_NOTE', 'fields': []}
        if matches:
            result = subprocess.run(['op', 'item', 'get', matches[0]['id'], '--vault', VAULT, '--format=json'],
                                    capture_output=True, text=True, check=True, timeout=30)
            item = json.loads(result.stdout)
            if item.get('category') != 'SECURE_NOTE':
                raise CredentialError('The existing backup item must be a Secure Note.')
        item['fields'] = [field for field in item.get('fields', [])
                          if field.get('label') != 'DOKPLOY_API_KEY' and field.get('id') != 'dokploy_api_key']
        item['fields'].append({'id': 'dokploy_api_key', 'label': 'DOKPLOY_API_KEY', 'type': 'CONCEALED', 'value': key})
        with tempfile.TemporaryDirectory(prefix='kengen-vault-') as directory:
            path = Path(directory) / 'item.json'
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
                json.dump(item, file)
            command = ['op', 'item', 'edit', matches[0]['id']] if matches else ['op', 'item', 'create']
            subprocess.run(command + ['--vault', VAULT, '--template', str(path)],
                           capture_output=True, check=True, timeout=30)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise CredentialError('The local key is retained. Unlock 1Password and retry deploy:credentials:save.') from None
    print('Dokploy key saved in 1Password: ' + BACKUP_ITEM)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-stdin', action='store_true', help='Cache a key supplied over stdin without printing it.')
    parser.add_argument('--save', action='store_true', help='Back up the cached key to 1Password once.')
    parser.add_argument('--prompt', action='store_true', help='Read a key from a hidden terminal prompt.')
    args = parser.parse_args()
    try:
        if args.prompt:
            key = getpass.getpass('Dokploy API key (hidden): ').strip()
            if not key:
                raise CredentialError('The key must not be empty.')
        elif args.from_stdin:
            import sys
            key = sys.stdin.read().strip()
            if not key or any(c in key for c in '\r\n\0'):
                raise CredentialError("Expected one nonempty Dokploy key on stdin.")
        else:
            key = obtain()
        cache(ROOT / 'mise.local.toml', {'DOKPLOY_API_KEY': key})
        if args.save:
            backup(key)
        print('Dokploy credential cached in mise.local.toml (0600). No vault access is needed on later runs.')
    except CredentialError as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
