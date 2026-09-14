"""Manage independent model and viewer versions without changing server releases."""
import argparse
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {'models': 'models/VERSION', 'viewer': 'internal/viewer/VERSION'}


def validate(version):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('Use a stable semantic version such as 1.2.3.')
    return version


def read(root, component):
    return validate((root / COMPONENTS[component]).read_text().strip())


def increment(version, part):
    major, minor, patch = map(int, validate(version).split('.'))
    if part == 'major':
        return f'{major + 1}.0.0'
    if part == 'minor':
        return f'{major}.{minor + 1}.0'
    if part == 'patch':
        return f'{major}.{minor}.{patch + 1}'
    raise ValueError('Choose major, minor, or patch.')


def bump(root, component, part):
    version = increment(read(root, component), part)
    (root / COMPONENTS[component]).write_text(version + '\n')
    return version


def tag_name(component, version):
    if component not in COMPONENTS:
        raise ValueError('Choose models or viewer.')
    return component + '/v' + validate(version)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def tag(component):
    if git('branch', '--show-current') != 'main' or git('status', '--porcelain'):
        raise ValueError('Create release tags from a clean, committed main checkout.')
    name = tag_name(component, read(ROOT, component))
    # git rejects existing tags; never move a published component version.
    git('tag', '-a', name, '-m', f'Release {component} {read(ROOT, component)}')
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('show')
    bump_parser = commands.add_parser('bump')
    bump_parser.add_argument('component', choices=COMPONENTS)
    bump_parser.add_argument('part', choices=('major', 'minor', 'patch'))
    tag_parser = commands.add_parser('tag')
    tag_parser.add_argument('component', choices=COMPONENTS)
    args = parser.parse_args()
    try:
        if args.command == 'show':
            for component in COMPONENTS:
                print(tag_name(component, read(ROOT, component)))
        elif args.command == 'bump':
            print(tag_name(args.component, bump(ROOT, args.component, args.part)))
            print('Review and commit the version change before creating its tag.')
        else:
            print(tag(args.component))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
