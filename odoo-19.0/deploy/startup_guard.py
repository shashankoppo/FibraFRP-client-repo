"""Refuse ordinary startup against an unfinished guarded deployment."""
import os
import sys
import psycopg2


def main():
    database = os.environ.get('ODOO_AUTO_UPDATE_DB_NAME') or os.environ.get('LIVE_DB_NAME')
    if not database:
        return
    with psycopg2.connect(host=os.environ['DB_HOST'], port=os.environ.get('DB_PORT', '5432'),
                          user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                          dbname=database) as conn, conn.cursor() as cr:
        cr.execute("SELECT to_regclass('elsx_deploy_installed_modules')")
        if cr.fetchone()[0]:
            raise RuntimeError('An unfinished deployment is in maintenance. Use the documented recovery procedure.')
        cr.execute("SELECT to_regclass('elsx_deploy_maintenance')")
        if cr.fetchone()[0]:
            cr.execute('SELECT state FROM elsx_deploy_maintenance')
            if cr.fetchall() != [('verified',)] or os.environ.get('DEPLOY_VERIFIED_START') != 'YES':
                raise RuntimeError('Deployment health checks are incomplete. Use explicit recovery.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Odoo startup refused: configured database unavailable or unfinished deployment. Check deployment metadata.', file=sys.stderr)
        sys.exit(1)
