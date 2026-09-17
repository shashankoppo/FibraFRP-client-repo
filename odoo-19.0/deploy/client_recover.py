"""Explicit recovery. Never drops, replaces, or automatically restores a database."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

from client_deploy import ROOT, compose, output, run, validate_config, deployment_lock, image_phase, db_command, sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'verify-and-start', 'resume-upgrade'])
    args = parser.parse_args()
    os.chdir(ROOT)
    config = json.loads(output(compose('config', '--format', 'json')))
    database = validate_config(config, 'production')
    directory = Path(os.environ['RECOVERY_DIR']).resolve()
    metadata = json.loads((directory / 'deployment.json').read_text(encoding='utf-8'))
    if metadata['database'] != database:
        raise ValueError('Recovery backup and configured production target do not match.')
    if args.action == 'inspect':
        print(json.dumps(metadata, indent=2))
        return
    with deployment_lock():
        backup = directory / 'backup.tar.enc'
        with backup.open('rb') as source:
            if sha256_file(source) != metadata.get('backup_sha256'):
                raise ValueError('Backup checksum mismatch or missing verified backup; recovery refused.')
        for service, key in [('odoo', 'volumes'), ('db', 'db_volumes')]:
            container = output(compose('ps', '--all', '-q', service))
            if len(container.splitlines()) != 1:
                raise ValueError('Recovery requires the original %s container.' % service)
            inspected = json.loads(output(['docker', 'inspect', container]))[0]
            mounts = {m['Destination']: m.get('Name') or m['Source'] for m in inspected['Mounts']}
            if mounts != metadata[key]:
                raise ValueError('Recovery refuses changed %s volume identities.' % service)
            for volume in config['services'][service].get('volumes', []):
                if volume['type'] == 'volume' and mounts.get(volume['target']) != config['volumes'][volume['source']]['name']:
                    raise ValueError('Recovery configuration would replace a persistent volume.')
        run(compose('stop', '-t', '120', 'odoo'))
        user = config['services']['db']['environment']['POSTGRES_USER']
        if output(db_command(user, 'postgres',
                "SELECT count(*) FROM pg_stat_activity WHERE datname='%s' AND backend_type='client backend'" % database)) != '0':
            raise ValueError('Stop remaining database clients before recovery.')
        os.environ['ODOO_IMAGE'] = metadata['candidate_tag']
        if output(['docker', 'image', 'inspect', metadata['candidate_tag'], '--format', '{{.Id}}']) != metadata['candidate_image']:
            raise ValueError('Candidate image tag changed since deployment; recovery refused.')
        if args.action == 'resume-upgrade':
            # The operator must first check out and validate the corrected revision.
            if output(['git', 'status', '--porcelain']):
                raise ValueError('Commit/review the recovery revision before rebuilding.')
            stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ').lower()
            os.environ['ODOO_IMAGE'] = 'odoo-custom:recovery-' + stamp
            run(compose('build', 'odoo'))
            metadata.setdefault('recovery_history', []).append({
                'candidate_tag': metadata['candidate_tag'], 'candidate_image': metadata['candidate_image'],
                'revision': metadata['revision'],
            })
            metadata.update(candidate_tag=os.environ['ODOO_IMAGE'],
                            candidate_image=output(['docker', 'image', 'inspect', os.environ['ODOO_IMAGE'], '--format', '{{.Id}}']),
                            revision=output(['git', 'rev-parse', 'HEAD']), stage='recovery_upgrade')
            (directory / 'deployment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
            run(image_phase(database, 'resume-upgrade'))
        run(image_phase(database, 'verify'))
        metadata['stage'] = 'verified'
        (directory / 'deployment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        try:
            os.environ['DEPLOY_VERIFIED_START'] = 'YES'
            run(compose('up', '-d', '--no-deps', '--wait', '--wait-timeout', '240', 'odoo'))
            run(['docker', 'image', 'tag', metadata['candidate_image'], 'odoo-custom:19.0'])
            run(image_phase(database, 'release'))
        except BaseException:
            run(compose('stop', '-t', '30', 'odoo'))
            raise
        metadata['stage'] = 'complete'
        (directory / 'deployment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print('Recovery verified. Existing database and filestore remain in place.')


if __name__ == '__main__':
    main()
