"""Build and deploy local main or a release tag through the Mac mini Dokploy API."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

import credentials
import deploy

ROOT = Path(__file__).resolve().parents[2]
HOST_ROOT = '/Users/hdb/homelab/kengen'


def run(argv, *, cwd=ROOT, data=None):
    environment = {k: v for k, v in os.environ.items()
                   if not any(part in k.upper() for part in ('TOKEN', 'PASSWORD', 'SECRET', 'API_KEY'))}
    try:
        result = subprocess.run(argv, cwd=cwd, input=data, capture_output=True, check=True, env=environment)
        return result.stdout
    except (OSError, subprocess.CalledProcessError):
        raise deploy.DeployError('Command failed: ' + Path(argv[0]).name + '. No credential values were logged.') from None


def source_commit(tag):
    if tag:
        deploy.validate_tag(tag)
        ref = 'refs/tags/' + tag
    else:
        ref = 'HEAD'
    commit = run(['git', 'rev-parse', '--verify', ref + '^{commit}']).decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise deploy.DeployError('Invalid source commit.')
    run(['git', 'merge-base', '--is-ancestor', commit, 'main'])
    if not tag and run(['git', 'status', '--porcelain']).strip():
        raise deploy.DeployError('Commit local changes before deployment. Local credential files must be ignored.')
    return commit


def host_environment():
    os.environ['PATH'] = '/Users/hdb/homelab/bin:/Users/hdb/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:' + os.environ.get('PATH', '')
    os.environ['DOCKER_HOST'] = 'unix:///Users/hdb/.orbstack/run/docker.sock'
    os.environ['DOCKER_CONFIG'] = '/Users/hdb/homelab/docker-config'
    os.environ['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
    # Do not load unrelated personal project hooks or vault-backed settings.
    os.environ['MISE_IGNORED_CONFIG_PATHS'] = '/Users/hdb/.config/mise/config.toml:/Users/hdb/Developer/nakamadevs/mise.toml:' + HOST_ROOT + '/mise.local.toml'


@contextmanager
def build_context(commit):
    if not (ROOT / '.git').exists():
        yield ROOT  # SSH already transferred this exact commit with git archive.
        return
    with tempfile.TemporaryDirectory(prefix='kengen-source-') as folder:
        context = Path(folder)
        archive = run(['git', 'archive', commit], cwd=ROOT)
        run(['tar', '-xf', '-', '-C', folder], cwd=ROOT, data=archive)
        yield context


def local_build(commit, version):
    print('Test deployment behavior and build Linux ARM64.', flush=True)
    run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'deploy/dokploy', '-p', 'test_*.py'])
    image = deploy.IMAGE + ':' + version
    with build_context(commit) as context:
        run(['docker', 'build', '--platform', 'linux/arm64', '--label', 'org.opencontainers.image.revision=' + commit,
             '--label', 'org.opencontainers.image.version=' + version, '-t', image, '.'], cwd=context)
    print('Scan the image for high and critical vulnerabilities.', flush=True)
    run(['mise', 'trust', '--yes', str(ROOT / 'mise.toml')])
    run(['mise', 'install', 'trivy'])
    run(['mise', 'exec', '--', 'trivy', 'image', '--scanners', 'vuln', '--severity', 'HIGH,CRITICAL',
         '--exit-code', '1', '--quiet', image])
    print('Push to the mini registry.', flush=True)
    run(['docker', 'push', image])
    refs = json.loads(run(['docker', 'image', 'inspect', '--format', '{{json .RepoDigests}}', image]))
    matches = [ref for ref in refs if ref.startswith(deploy.IMAGE + '@sha256:')]
    if len(matches) != 1:
        raise deploy.DeployError('Cannot resolve the published image digest.')
    return matches[0]


def on_host(args, key):
    host_environment()
    if run(['hostname', '-s']).decode().strip() != 'hdbmm' or run(['uname', '-m']).decode().strip() != 'arm64':
        raise deploy.DeployError('The deployment must run on hdbmm ARM64.')
    api = deploy.API('http://localhost:3000', key)
    compose_id = os.environ.get('KENGEN_DOKPLOY_COMPOSE_ID') or 'Rngd-n1Wq6CMj3uPIe7Q_'
    if args.status:
        current = api.call('GET', 'compose.one', {'composeId': compose_id})
        deploy.verify_service(current, compose_id)
        print('Kengen Dokploy status:', current.get('composeStatus'))
        deploy.check_health()
        print('HTTPS health: SERVING')
        return
    commit = args.commit or source_commit(args.tag)
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise deploy.DeployError('Invalid source commit.')
    deploy.validate_direct_credentials()
    image = args.image or local_build(commit, args.tag or 'main-' + commit[:12])
    deploy.verify_image(image, commit)
    compose_id = deploy.ensure_service(api, compose_id, {}, image, auth_mode='preshared')
    print('Update Kengen through the Dokploy API.', flush=True)
    deploy.deploy(api, compose_id, image, {}, Path.home() / '.kengen/dokploy-snapshots', auth_mode='preshared')
    run([sys.executable, '-B', 'deploy/dokploy/smoke.py'])
    print('Deployed and tested https://' + deploy.HOST)
    print('Image:', image)


def remote(args, key):
    commit = source_commit(args.tag)
    host = os.environ.get('KENGEN_SSH_HOST', 'macmini')
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._@-]*', host):
        raise deploy.DeployError('Invalid KENGEN_SSH_HOST.')
    path = HOST_ROOT + '/releases/' + commit
    ssh = ['ssh', '-o', 'BatchMode=yes', host]
    archive = run(['git', 'archive', commit])
    run(ssh + ['mkdir -p ' + shlex.quote(path) + ' && tar -xf - -C ' + shlex.quote(path)], data=archive)
    # Supply the credential over SSH stdin, never argv or an archive.
    bootstrap = "import os,sys; sys.path.insert(0," + repr(path + '/deploy/dokploy') + "); import credentials; from pathlib import Path; credentials.cache(Path(" + repr(HOST_ROOT + '/mise.local.toml') + "), {'DOKPLOY_API_KEY':sys.stdin.read().strip()})"
    run(ssh + ['/opt/homebrew/bin/python3 -c ' + shlex.quote(bootstrap)], data=key.encode())
    argv = ['/opt/homebrew/bin/python3', '-B', path + '/deploy/dokploy/manage.py', '--on-host', '--commit', commit]
    if args.tag:
        argv += ['--tag', args.tag]
    if args.image:
        argv += ['--image', args.image]
    if args.status:
        argv += ['--status']
    # The remote controller emits only safe progress. Keep the SSH output live.
    result = subprocess.run(ssh + ['cd ' + shlex.quote(path) + ' && ' + shlex.join(argv)])
    if result.returncode:
        raise deploy.DeployError('The Mac mini deployment failed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', help='Release tag on main; defaults to committed local main.')
    parser.add_argument('--image', help='Use an existing immutable image for this commit.')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--check-ref', action='store_true', help='Validate the source without credentials or deployment.')
    parser.add_argument('--on-host', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--commit', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if sys.platform == 'darwin':
            os.environ.setdefault('SSL_CERT_FILE', '/etc/ssl/cert.pem')
        if args.check_ref:
            print('Source is on local main:', source_commit(args.tag))
            return
        is_host = args.on_host or os.uname().nodename.split('.')[0] == 'hdbmm'
        if args.commit and not args.on_host:
            raise deploy.DeployError('--commit is reserved for the SSH transfer.')
        cache_path = Path(HOST_ROOT) / 'mise.local.toml' if is_host else ROOT / 'mise.local.toml'
        key = credentials.obtain(cache_path)
        if args.status and not is_host:
            api = deploy.API('https://dokploy.lecksfrawen.com', key)
            compose_id = os.environ.get('KENGEN_DOKPLOY_COMPOSE_ID') or 'Rngd-n1Wq6CMj3uPIe7Q_'
            current = api.call('GET', 'compose.one', {'composeId': compose_id})
            deploy.verify_service(current, compose_id)
            deploy.check_health()
            print('Kengen Dokploy status:', current.get('composeStatus'))
            print('HTTPS health: SERVING')
            return
        if is_host:
            on_host(args, key)
        else:
            remote(args, key)
    except (deploy.DeployError, credentials.CredentialError) as error:
        raise SystemExit(str(error)) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Deployment failed. Inspect the Kengen deployment in Dokploy.') from None


if __name__ == '__main__':
    main()
