"""One configured target, immutable images, and explicit maintenance upgrades."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def output(args):
    return run(args, stdout=subprocess.PIPE, text=True).stdout.strip()


def compose(*args):
    return ['docker', 'compose', *args]


def sha256_file(source):
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def initial_modules(settings):
    selected = settings.get('new_install_modules') or settings.get('install_modules', '')
    if settings.get('new_install_modules') and settings.get('install_modules') and selected != settings['install_modules']:
        raise ValueError('Conflicting NEW_INSTALL_MODULES and legacy INSTALL_MODULES values.')
    return selected


def target(config, mode):
    settings = config.get('x-deployment', {})
    names = [settings.get('database'), settings.get('legacy_database')]
    if mode == 'new':
        names = [settings.get('new_database')]
    names = {str(name).strip() for name in names if name}
    if len(names) != 1:
        raise ValueError('Configure one database target in the VPS/CI environment; conflicting or missing targets are refused.')
    name = names.pop()
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}', name) or name.lower() in {
        'postgres', 'template0', 'template1', 'your_client_db_name', 'new_db_name', 'your_db_name',
    }:
        raise ValueError('Invalid or placeholder database target.')
    return name


def validate_config(config, mode):
    name = target(config, mode)
    settings = config.get('x-deployment', {})
    env = config['services']['odoo'].get('environment', {})
    if mode == 'production':
        if any((settings.get('install_modules'), env.get('ODOO_AUTO_INSTALL_MODULES'),
                os.environ.get('EXTRA_INSTALL_MODULES'))):
            raise ValueError('Production deployment cannot install modules. Remove installation options.')
        if str(env.get('ODOO_AUTO_ALLOW_INSTALL', 'NO')).upper() == 'YES':
            raise ValueError('ODOO_AUTO_ALLOW_INSTALL must be NO in production.')
        if not settings.get('backup_passphrase'):
            raise ValueError('Configure BACKUP_PASSPHRASE in VPS/CI secrets before deployment.')
        for volume in config['services']['odoo'].get('volumes', []):
            if volume.get('type') == 'bind' and volume.get('target', '').startswith('/opt/odoo'):
                raise ValueError('Production addon/source bind mounts are refused; include addons in the image.')
    else:
        if not env.get('DB_PASSWORD') or env['DB_PASSWORD'] == 'odoo':
            raise ValueError('New environments require an explicit, non-default POSTGRES_PASSWORD.')
        if not re.fullmatch(r'[A-Za-z0-9_]+', name):
            raise ValueError('New database names must contain only letters, numbers and underscores.')
        production_targets = {str(value).strip() for value in
                              (settings.get('database'), settings.get('legacy_database')) if value}
        if production_targets - {name}:
            raise ValueError('New installation conflicts with the configured production database target.')
        modules = initial_modules(settings)
        if not modules or not re.fullmatch(r'[a-zA-Z0-9_]+(?:,[a-zA-Z0-9_]+)*', modules):
            raise ValueError('New environments require an explicit NEW_INSTALL_MODULES list.')
        if 'elsx_client_restrictions' not in modules.split(','):
            raise ValueError('Include elsx_client_restrictions in NEW_INSTALL_MODULES to protect Apps.')
        if not settings.get('admin_password'):
            raise ValueError('Configure NEW_DB_ADMIN_PASSWORD in VPS/CI secrets.')
    return name


def db_command(user, database, sql):
    return compose('exec', '-T', 'db', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                   '-U', user, '-d', database, '-Atc', sql)


def image_phase(database, phase):
    return compose('run', '--rm', '-T', '--no-deps', '-e', 'DEPLOY_DB=' + database,
                   '--entrypoint', 'python3', 'odoo', '/opt/odoo/deploy/guarded_upgrade.py', phase)


@contextlib.contextmanager
def deployment_lock():
    path = ROOT / 'secure_backups' / '.deployment.lock'
    path.parent.mkdir(mode=0o700, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            handle.seek(0)
            handle.write(b'0')
            handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def backup(database, user, passphrase, directory, manifest):
    """Caller has stopped all writers. Verify decryption and archive contents."""
    with tempfile.TemporaryDirectory(prefix='bundle-', dir=directory) as temp:
        stage = Path(temp)
        dump = stage / 'database.dump'
        with dump.open('wb') as dest:
            run(compose('exec', '-T', 'db', 'pg_dump', '-U', user, '-d', database, '-Fc'), stdout=dest)
        with dump.open('rb') as source:
            run(compose('exec', '-T', 'db', 'pg_restore', '--list'), stdin=source, stdout=subprocess.DEVNULL)
        # This runner reads the configured Odoo data_dir, not a hard-coded user home.
        with (stage / 'filestore.tar').open('wb') as dest:
            run(image_phase(database, 'filestore'), stdout=dest)
        with tarfile.open(stage / 'filestore.tar') as archive:
            archive.getmembers()
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        for name in ('docker-compose.yml', 'odoo.docker.conf', '.env'):
            source = ROOT / name
            if source.is_file():
                shutil.copy2(source, stage / name)
        plain = stage / 'bundle.tar'
        with tarfile.open(plain, 'w') as archive:
            for source in stage.iterdir():
                if source != plain:
                    archive.add(source, arcname=source.name)
        encrypted = directory / 'backup.tar.enc'
        secret_env = dict(os.environ, DEPLOY_BACKUP_SECRET=passphrase)
        base = ['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-iter', '200000', '-pass', 'env:DEPLOY_BACKUP_SECRET']
        run(base + ['-salt', '-in', str(plain), '-out', str(encrypted)], env=secret_env)
        encrypted.chmod(0o600)
        verified = stage / 'verified.tar'
        run(base + ['-d', '-in', str(encrypted), '-out', str(verified)], env=secret_env)
        with plain.open('rb') as a, verified.open('rb') as b:
            if sha256_file(a) != sha256_file(b):
                raise RuntimeError('Backup verification failed.')
        with encrypted.open('rb') as source:
            manifest['backup_sha256'] = sha256_file(source)
        return encrypted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['production', 'new'])
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    os.chdir(ROOT)
    config = json.loads(output(compose('config', '--format', 'json')))
    database = validate_config(config, args.mode)
    if args.mode == 'production' and not shutil.which('openssl'):
        raise ValueError('Install openssl on the VPS before deployment.')
    user = config['services']['db']['environment']['POSTGRES_USER']
    settings = config['x-deployment']
    with deployment_lock():
        dirty = output(['git', 'status', '--porcelain', '--untracked-files=normal'])
        if dirty and not args.preflight:
            raise ValueError('Working tree is not clean. Review and commit deployment inputs first.')
        if args.mode == 'production':
            current = output(compose('ps', '--all', '-q', 'odoo'))
            if not current or len(current.splitlines()) != 1:
                raise ValueError('Expected one existing Odoo container; refusing to guess the deployment.')
            deployed = json.loads(output(['docker', 'inspect', current]))[0]
            if deployed['State']['Running'] and any(
                    m['Type'] == 'bind' and m['Destination'].startswith('/opt/odoo') for m in deployed['Mounts']):
                raise ValueError('Legacy source-mounted deployment: stop Odoo before pulling or checking out code. Then run this command again.')
        if not args.preflight and not os.environ.get('CI') and os.environ.get('NO_PULL') != 'YES':
            run(['git', 'pull', '--ff-only', 'origin', 'main'])
            # Execute the runner from the new revision, keeping its validation authoritative.
            os.environ['NO_PULL'] = 'YES'
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), args.mode])
        dirty = output(['git', 'status', '--porcelain', '--untracked-files=normal'])
        if dirty and not args.preflight:
            raise ValueError('Working tree is not clean. Review and commit deployment inputs first.')
        if args.mode == 'new' and not args.preflight:
            if output(compose('ps', '--all', '-q', 'odoo')):
                raise ValueError('New installation requires a fresh Compose environment, not an existing client service.')
            run(compose('up', '-d', '--wait', 'db'))
        exists = output(db_command(user, 'postgres', "SELECT count(*) FROM pg_database WHERE datname = '%s'" % database))
        if args.mode == 'new':
            if exists != '0':
                raise ValueError('The database already exists; new installation refuses to overwrite it.')
            if args.preflight:
                print('New database target and explicit module list validated.')
                return
            os.environ.update(NEW_DB_ADMIN_PASSWORD=settings['admin_password'],
                              INSTALL_MODULES=initial_modules(settings), POSTGRES_USER=user)
            run(['bash', 'deploy/create_client_database.sh', database, os.environ.get('COUNTRY', 'IN'),
                 os.environ.get('ADMIN_LOGIN', 'admin')], env=dict(os.environ, CONFIRM_CREATE_DB='YES'))
            return
        if exists != '1':
            raise ValueError('Configured production database does not exist; nothing will be created.')
        container = output(compose('ps', '--all', '-q', 'odoo'))
        if not container:
            raise ValueError('No existing Odoo service. Use the documented recovery procedure before deployment.')
        old = json.loads(output(['docker', 'inspect', container]))[0]
        volumes = {mount['Destination']: mount.get('Name') or mount['Source'] for mount in old['Mounts']}
        configured_volumes = {v['target']: config['volumes'][v['source']]['name']
                              for v in config['services']['odoo'].get('volumes', []) if v['type'] == 'volume'}
        if any(volumes.get(path) != name for path, name in configured_volumes.items()):
            raise ValueError('Configured data volumes differ from the running service; refusing replacement.')
        db_container = output(compose('ps', '-q', 'db'))
        db_inspect = json.loads(output(['docker', 'inspect', db_container]))[0]
        db_mounts = {m['Destination']: m.get('Name') or m['Source'] for m in db_inspect['Mounts']}
        for volume in config['services']['db'].get('volumes', []):
            if volume['type'] == 'volume' and db_mounts.get(volume['target']) != config['volumes'][volume['source']]['name']:
                raise ValueError('PostgreSQL volume identity changed; refusing deployment.')
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        directory = ROOT / 'secure_backups' / (database + '-' + stamp)
        directory.mkdir(mode=0o700)
        manifest = {'database': database, 'revision': output(['git', 'rev-parse', 'HEAD']),
                    'previous_image': old['Image'], 'volumes': volumes, 'db_volumes': db_mounts, 'stage': 'preflight'}
        maintenance = False
        try:
            if not args.preflight:
                candidate = 'odoo-custom:candidate-' + stamp.lower()
                os.environ['ODOO_IMAGE'] = candidate
                run(compose('build', 'odoo'))
                image_id = output(['docker', 'image', 'inspect', candidate, '--format', '{{.Id}}'])
                manifest.update(candidate_image=image_id, candidate_tag=candidate)
            report = json.loads(output(image_phase(database, 'preflight')))
            manifest['preflight'] = report
            if shutil.disk_usage(directory).free < report['backup_bytes_required']:
                raise ValueError('Insufficient backup disk space; keep at least six times DB and filestore size free.')
            if args.preflight:
                print(json.dumps(report, indent=2))
                return
            run(['docker', 'image', 'tag', old['Image'], 'odoo-custom:rollback-' + stamp.lower()])
            # Existing legacy sidecars are deliberately left running; Meta retries while Odoo is stopped.
            run(compose('stop', '-t', '120', 'odoo'))
            maintenance = True
            manifest['stage'] = 'maintenance'
            remaining = output(db_command(user, 'postgres',
                "SELECT count(*) FROM pg_stat_activity WHERE datname='%s' AND backend_type='client backend'" % database))
            if remaining != '0':
                raise ValueError('Other database clients remain connected. Stop all writers/workers before backing up.')
            backup(database, user, settings['backup_passphrase'], directory, manifest)
            manifest['stage'] = 'backed_up'
            # Recheck under maintenance and install a DB-level guard before Odoo can change module states.
            run(image_phase(database, 'upgrade'))
            run(image_phase(database, 'verify'))
            manifest['stage'] = 'verified'
            os.environ['DEPLOY_VERIFIED_START'] = 'YES'
            run(compose('up', '-d', '--no-deps', '--wait', '--wait-timeout', '240', 'odoo'))
            # The default startup alias follows only a successfully verified candidate.
            run(['docker', 'image', 'tag', manifest['candidate_image'], 'odoo-custom:19.0'])
            run(image_phase(database, 'release'))
            maintenance = False
            manifest['stage'] = 'complete'
            print('Deployment complete for %s. Backup: %s' % (database, directory / 'backup.tar.enc'))
        except BaseException:
            if maintenance:
                run(compose('stop', '-t', '30', 'odoo'))
                print('Deployment stopped in maintenance. Database/volumes preserved. Recovery metadata: ' + str(directory), file=sys.stderr)
            raise
        finally:
            (directory / 'deployment.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        # Never print Compose's resolved configuration or credentials.
        print('Deployment failed: %s' % exc, file=sys.stderr)
        sys.exit(1)
