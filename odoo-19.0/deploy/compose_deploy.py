"""Run the existing deployment guard from a one-off local Linux Compose service."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


def deployment_context(inspected, project_dir, mode):
    """Bind paths must mean the same thing to this container and the host daemon."""
    project = PurePosixPath(project_dir)
    labels = inspected.get('Config', {}).get('Labels', {}) or {}
    service = 'deploy-prod' if mode == 'production' else 'deploy-new'
    if (not project.is_absolute() or '..' in project.parts or len(project.parts) < 3
            or labels.get('com.docker.compose.service') != service
            or labels.get('com.docker.compose.oneoff', '').lower() != 'true'):
        raise ValueError('Use docker compose run --rm --build %s from the Linux VPS project directory.' % service)
    if labels.get('com.docker.compose.project.working_dir') != str(project):
        raise ValueError('Compose working directory differs from the mounted checkout; deployment refused.')
    mounts = inspected.get('Mounts', [])
    if not any(m.get('Type') == 'bind' and m.get('RW')
               and m.get('Source') == str(project.parent)
               and m.get('Destination') == str(project.parent) for m in mounts):
        raise ValueError('Checkout must be mounted at its exact host path. Use a physical (not symlinked) Linux VPS directory.')
    if not any(m.get('Type') == 'bind' and m.get('Source') == '/var/run/docker.sock'
               and m.get('Destination') == '/var/run/docker.sock' for m in mounts):
        raise ValueError('Deployment requires the local VPS Docker socket.')
    project_name = labels.get('com.docker.compose.project')
    files = labels.get('com.docker.compose.project.config_files', '').split(',')
    env_files = labels.get('com.docker.compose.project.environment_file', '')
    if not project_name or not all(files):
        raise ValueError('Missing Compose project identity/configuration; refusing to guess.')
    for name in files + ([p for p in env_files.split(',') if p] if env_files else []):
        path = PurePosixPath(name)
        if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(project.parent):
            raise ValueError('Compose configuration/env files must be within the mounted repository.')
    for name in [p for p in env_files.split(',') if p]:
        filename = PurePosixPath(name).name
        if not (filename == '.env' or filename.startswith('.env.') or filename.endswith('.env')):
            raise ValueError('Secret env files must use .env, .env.* or *.env names excluded from Docker builds.')
    return {'COMPOSE_PROJECT_NAME': project_name, 'COMPOSE_FILE': ':'.join(files),
            'COMPOSE_PATH_SEPARATOR': ':', 'COMPOSE_ENV_FILES': env_files, 'PWD': str(project),
            'NO_PULL': 'YES', 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'safe.directory',
            'GIT_CONFIG_VALUE_0': str(project.parent), 'GIT_OPTIONAL_LOCKS': '0'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['production', 'new'])
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix' or not os.environ.get('ELSX_DEPLOY_HOST_DIR', '').startswith('/'):
        raise ValueError('Run on the Alpine/Ubuntu VPS from odoo-19.0 with PWD exported, not from a remote Docker context.')
    project = Path(__file__).resolve().parents[1]
    if str(project) != os.environ['ELSX_DEPLOY_HOST_DIR']:
        raise ValueError('PWD and checkout differ. Enter the physical odoo-19.0 directory before deployment.')
    os.environ['DOCKER_HOST'] = 'unix:///var/run/docker.sock'
    inspected = json.loads(subprocess.check_output(
        ['docker', 'inspect', os.environ['HOSTNAME']], text=True))[0]
    context = deployment_context(inspected, str(project), args.mode)
    for filename in context['COMPOSE_FILE'].split(':') + [p for p in context['COMPOSE_ENV_FILES'].split(',') if p]:
        if not Path(filename).is_file():
            raise ValueError('A required Compose configuration file is unavailable inside the deployment service.')
    os.environ.update(context)
    os.chdir(project)
    command = [sys.executable, str(project / 'deploy/client_deploy.py'), args.mode]
    if args.preflight:
        command.append('--preflight')
    os.execv(sys.executable, command)


if __name__ == '__main__':
    try:
        main()
    except ValueError as exc:
        print('Compose deployment refused: %s No upgrade was started.' % exc, file=sys.stderr)
        sys.exit(1)
    except (OSError, KeyError, subprocess.CalledProcessError):
        # Never include resolved Compose configuration or secret environment values.
        print('Compose deployment refused: check the local VPS path, one-off command, socket and configuration. No upgrade was started.', file=sys.stderr)
        sys.exit(1)
