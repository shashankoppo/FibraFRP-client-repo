"""Runs inside the candidate image. Never creates or replaces a client DB."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import psycopg2
from integrity import snapshot, assert_unchanged

ROOT = Path('/opt/odoo')
sys.path.insert(0, str(ROOT))


def configuration():
    import odoo
    from odoo.tools import config
    addons = os.environ.get('ODOO_ADDONS_PATH', '/opt/odoo/addons,/opt/odoo/odoo/addons,/opt/odoo/custom_addons,/opt/odoo/third_party_addons')
    if os.environ.get('ODOO_EXTRA_ADDONS_PATH'):
        addons += ',' + os.environ['ODOO_EXTRA_ADDONS_PATH']
    args = ['-c', os.environ.get('ODOO_RC', '/etc/odoo/odoo.conf'),
            '--addons-path=' + addons, '--db_host=' + os.environ['DB_HOST'],
            '--db_port=' + os.environ.get('DB_PORT', '5432'),
            '--db_user=' + os.environ['DB_USER'], '--db_password=' + os.environ['DB_PASSWORD']]
    config.parse_config(args)
    return config, args, addons.split(',')


def connection(database):
    return psycopg2.connect(dbname=database, host=os.environ['DB_HOST'],
                            port=os.environ.get('DB_PORT', '5432'), user=os.environ['DB_USER'],
                            password=os.environ['DB_PASSWORD'])


def installed(cr):
    cr.execute("SELECT name, state FROM ir_module_module WHERE state IN ('installed', 'to upgrade', 'to install', 'to remove') ORDER BY name")
    rows = cr.fetchall()
    if any(state in ('to install', 'to remove') for _, state in rows):
        raise RuntimeError('Pending module installation/removal must be resolved before deployment.')
    if not rows or 'base' not in dict(rows):
        raise RuntimeError('Target is not an initialized Odoo database.')
    return dict(rows)


def verify_requested_modules(cr, names):
    if not names:
        raise RuntimeError('An explicit initial module list is required for verification.')
    cr.execute('SELECT name, state FROM ir_module_module WHERE name=ANY(%s)', [names])
    actual = dict(cr.fetchall())
    missing = [name for name in names if actual.get(name) != 'installed']
    if missing:
        raise RuntimeError('Requested modules are missing or not installed: ' + ', '.join(missing))


def verify_apps_guard(modules):
    if modules.get('elsx_client_restrictions') not in ('installed', 'to upgrade'):
        raise RuntimeError('Apps guard elsx_client_restrictions is not installed. Production will not install it automatically; arrange an explicitly approved initial installation first.')


def access_report(cr):
    cr.execute("SELECT to_regclass('whatsapp_account')")
    if not cr.fetchone()[0]:
        return {}
    cr.execute('SELECT id FROM res_company ORDER BY id')
    companies = [row[0] for row in cr.fetchall()]
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='whatsapp_account'")
    has_company = 'company_id' in {row[0] for row in cr.fetchall()}
    cr.execute('SELECT id%s FROM whatsapp_account ORDER BY id' % (', company_id' if has_company else ''))
    accounts = cr.fetchall()
    cr.execute("SELECT value FROM ir_config_parameter WHERE key='whatsapp.account.company_mapping'")
    configured = cr.fetchone()
    mapping = json.loads(configured[0]) if configured else {}
    report = {}
    for row in accounts:
        account_id = row[0]
        cr.execute('''SELECT DISTINCT user_id FROM whatsapp_team_member WHERE account_id=%s
                      UNION SELECT DISTINCT assigned_user_id FROM whatsapp_chat
                      WHERE account_id=%s AND assigned_user_id IS NOT NULL''', [account_id, account_id])
        agents = [r[0] for r in cr.fetchall()]
        company = (row[1] if has_company else None) or mapping.get(str(account_id)) or (companies[0] if len(companies) == 1 else None)
        if company not in companies:
            raise RuntimeError('WhatsApp account %s requires an explicit company mapping before deployment.' % account_id)
        if agents:
            cr.execute('''SELECT id FROM res_users WHERE id=ANY(%s) AND active
                          AND (share OR NOT EXISTS (SELECT 1 FROM res_company_users_rel r
                               WHERE r.user_id=res_users.id AND r.cid=%s))''', [agents, company])
            if cr.fetchall():
                raise RuntimeError('WhatsApp account %s has agents without internal/company access. Resolve the mapping before deployment.' % account_id)
        cr.execute('SELECT app_secret, skip_webhook_hmac FROM whatsapp_account WHERE id=%s', [account_id])
        secret, skip = cr.fetchone()
        if not secret:
            raise RuntimeError('Configure Meta app secret on WhatsApp account %s before enforcing production HMAC.' % account_id)
        # Without evidence, preserve no broad internal-user access by guessing.
        cr.execute('SELECT count(*) FROM whatsapp_chat WHERE account_id=%s', [account_id])
        if cr.fetchone()[0] and not agents:
            raise RuntimeError('Map an existing WhatsApp team for account %s before tightening access.' % account_id)
        report[str(account_id)] = {'company_id': company, 'agent_ids': sorted(agents), 'hmac_bypass_will_be_disabled': bool(skip)}
    return report


def preflight(cr, database, config, paths):
    if config['db_name'] != [database]:
        cr.execute("SELECT datname FROM pg_database WHERE NOT datistemplate AND datname NOT IN (%s, 'postgres')", [database])
        for (other_database,) in cr.fetchall():
            with connection(other_database) as other, other.cursor() as other_cr:
                other_cr.execute("SELECT to_regclass('public.ir_module_module')")
                if other_cr.fetchone()[0]:
                    raise RuntimeError('Other initialized databases share an unpinned Odoo service. Review a per-database rollout before deploying.')
    modules = installed(cr)
    verify_apps_guard(modules)
    for name in modules:
        path = next((Path(root) / name / '__manifest__.py' for root in paths
                     if (Path(root) / name / '__manifest__.py').is_file()), None)
        if not path:
            raise RuntimeError('Installed addon missing from candidate image: ' + name)
        manifest = ast.literal_eval(path.read_text(encoding='utf-8-sig'))
        missing = set(manifest.get('depends', [])) - modules.keys()
        if missing or not manifest.get('installable', True):
            raise RuntimeError('Installed addon %s requires review: missing dependencies %s or not installable.' % (name, sorted(missing)))
    cr.execute('SELECT pg_database_size(%s)', [database])
    size = cr.fetchone()[0]
    filestore = Path(config['data_dir']) / 'filestore' / database
    size += sum(file.stat().st_size for file in filestore.rglob('*') if file.is_file()) if filestore.exists() else 0
    cr.execute("SELECT value FROM ir_config_parameter WHERE key='whatsapp.realtime.mode'")
    mode = cr.fetchone()
    return {'installed_modules': sorted(modules), 'access_mapping': access_report(cr),
            'realtime_mode': mode[0] if mode else 'bus', 'backup_bytes_required': max(size * 6, 1024 ** 3)}


def install_guard(cr, names):
    cr.execute("SELECT to_regclass('elsx_deploy_installed_modules')")
    if cr.fetchone()[0]:
        raise RuntimeError('An earlier deployment guard remains. Review its failure and recover before retrying.')
    cr.execute('CREATE TABLE elsx_deploy_installed_modules (name varchar PRIMARY KEY)')
    cr.executemany('INSERT INTO elsx_deploy_installed_modules(name) VALUES (%s)', [(name,) for name in names])
    cr.execute('''CREATE FUNCTION elsx_guard_module_state() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF EXISTS (SELECT 1 FROM elsx_deploy_installed_modules WHERE name=OLD.name) THEN
                    RAISE EXCEPTION 'Deployment cannot delete installed module %', OLD.name;
                END IF;
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.name IS DISTINCT FROM OLD.name AND EXISTS
                (SELECT 1 FROM elsx_deploy_installed_modules WHERE name=OLD.name) THEN
                RAISE EXCEPTION 'Deployment cannot rename installed module %', OLD.name;
            END IF;
            IF NEW.state IN ('to install', 'to remove') OR
               (NEW.state IN ('installed', 'to upgrade') AND NOT EXISTS
                    (SELECT 1 FROM elsx_deploy_installed_modules WHERE name=NEW.name)) OR
               (NEW.state NOT IN ('installed', 'to upgrade') AND EXISTS
                    (SELECT 1 FROM elsx_deploy_installed_modules WHERE name=NEW.name)) THEN
                RAISE EXCEPTION 'Installed-only deployment rejected module % state %', NEW.name, NEW.state;
            END IF;
            RETURN NEW;
        END $$''')
    cr.execute('''CREATE TRIGGER elsx_guard_module_state BEFORE INSERT OR UPDATE OR DELETE
                  ON ir_module_module FOR EACH ROW EXECUTE FUNCTION elsx_guard_module_state()''')


def verify(cr, database):
    cr.execute('SELECT name FROM elsx_deploy_installed_modules ORDER BY name')
    expected = [row[0] for row in cr.fetchall()]
    actual = installed(cr)
    if sorted(actual) != expected or any(state != 'installed' for state in actual.values()):
        raise RuntimeError('Installed module set/states changed during upgrade; keeping maintenance active.')
    import odoo
    from odoo import api, SUPERUSER_ID
    registry = odoo.modules.registry.Registry(database)
    with registry.cursor() as check_cr:
        env = api.Environment(check_cr, SUPERUSER_ID, {})
        if not hasattr(env['ir.module.module'], '_elsx_require_apps_unlocked'):
            raise RuntimeError('Apps password guard is missing from the registry.')
        if 'elsx_whatsapp_marketing' in actual:
            for model in ('whatsapp.chat', 'whatsapp.message', 'whatsapp.account', 'whatsapp.webhook.log'):
                env[model].search([], limit=1).read(['id'])
            if 'whatsapp_realtime_mode' not in env['res.config.settings']._fields:
                raise RuntimeError('WhatsApp settings registry is incomplete.')
            env['whatsapp.chat'].get_view(view_type='form')
            env['res.config.settings'].get_view(view_type='form')
    from odoo.tools import config
    cr.execute('SELECT baseline FROM elsx_deploy_integrity')
    assert_unchanged(cr, config['data_dir'], database, cr.fetchone()[0])
    cr.execute('DROP TRIGGER elsx_guard_module_state ON ir_module_module')
    cr.execute('DROP FUNCTION elsx_guard_module_state()')
    cr.execute('DROP TABLE elsx_deploy_installed_modules')
    cr.execute('DROP TABLE elsx_deploy_integrity')
    cr.execute("UPDATE elsx_deploy_maintenance SET state='verified'")


def main():
    database = os.environ['DEPLOY_DB']
    phase = sys.argv[1]
    config, args, paths = configuration()
    with connection(database) as conn, conn.cursor() as cr:
        if phase == 'preflight':
            print(json.dumps(preflight(cr, database, config, paths)))
        elif phase == 'verify-new':
            verify_apps_guard(installed(cr))
            verify_requested_modules(cr, [name for name in os.environ.get('EXPECTED_INSTALL_MODULES', '').split(',') if name])
        elif phase == 'filestore':
            path = Path(config['data_dir']) / 'filestore' / database
            cr.execute("SELECT count(*) FROM ir_attachment WHERE store_fname IS NOT NULL")
            if cr.fetchone()[0] and not path.is_dir():
                raise RuntimeError('Attachments reference a missing filestore; backup refused.')
            with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as archive:
                if path.is_dir():
                    archive.add(path, arcname=database)
        elif phase in ('upgrade', 'resume-upgrade'):
            report = preflight(cr, database, config, paths)
            if phase == 'upgrade':
                cr.execute('CREATE TABLE elsx_deploy_maintenance (state varchar NOT NULL)')
                cr.execute("INSERT INTO elsx_deploy_maintenance VALUES ('upgrading')")
                install_guard(cr, report['installed_modules'])
                cr.execute('CREATE TABLE elsx_deploy_integrity (baseline jsonb NOT NULL)')
                cr.execute('INSERT INTO elsx_deploy_integrity VALUES (%s)', [json.dumps(snapshot(cr, config['data_dir'], database))])
            else:
                cr.execute('SELECT name FROM elsx_deploy_installed_modules ORDER BY name')
                if [row[0] for row in cr.fetchall()] != report['installed_modules']:
                    raise RuntimeError('Recovery refuses a changed installed module set.')
                cr.execute('SELECT count(*) FROM elsx_deploy_integrity')
                if cr.fetchone()[0] != 1:
                    raise RuntimeError('Original integrity baseline missing.')
            conn.commit()
            from odoo.orm.registry import Registry
            config['max_cron_threads'] = 0
            Registry.new(database, update_module=True, upgrade_modules=report['installed_modules'])
        elif phase == 'verify':
            cr.execute("SELECT to_regclass('elsx_deploy_installed_modules')")
            if cr.fetchone()[0]:
                verify(cr, database)
            else:
                cr.execute('SELECT state FROM elsx_deploy_maintenance')
                if cr.fetchall() != [('verified',)]:
                    raise RuntimeError('No verified deployment exists to resume.')
        elif phase == 'release':
            cr.execute('SELECT state FROM elsx_deploy_maintenance')
            if cr.fetchall() != [('verified',)]:
                raise RuntimeError('Refusing to release an unverified deployment.')
            cr.execute('DROP TABLE elsx_deploy_maintenance')
        else:
            raise RuntimeError('Unknown deployment phase.')


if __name__ == '__main__':
    main()
