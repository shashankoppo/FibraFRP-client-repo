"""Run only against an explicitly configured, disposable test PostgreSQL instance."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock

import psycopg2
from psycopg2 import sql

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
import guarded_upgrade
from integrity import snapshot, assert_unchanged


class NewInstallVerificationTests(unittest.TestCase):
    def test_apps_guard_missing_is_rejected_without_installing(self):
        for state in (None, 'uninstalled', 'to install', 'to remove'):
            with self.assertRaises(RuntimeError):
                guarded_upgrade.verify_apps_guard({'base': 'installed', 'elsx_client_restrictions': state})
        guarded_upgrade.verify_apps_guard({'elsx_client_restrictions': 'installed'})
        guarded_upgrade.verify_apps_guard({'elsx_client_restrictions': 'to upgrade'})

    def test_missing_or_uninstalled_requested_addon_is_rejected(self):
        cr = Mock()
        for rows in [[('base', 'installed')], [('base', 'installed'), ('sale', 'uninstalled')]]:
            cr.fetchall.return_value = rows
            with self.assertRaises(RuntimeError):
                guarded_upgrade.verify_requested_modules(cr, ['base', 'sale'])

    def test_requested_installed_addons_pass(self):
        cr = Mock()
        cr.fetchall.return_value = [('base', 'installed'), ('sale', 'installed')]
        guarded_upgrade.verify_requested_modules(cr, ['base', 'sale'])

    def test_empty_module_verification_is_rejected(self):
        with self.assertRaises(RuntimeError):
            guarded_upgrade.verify_requested_modules(Mock(), [])


@unittest.skipUnless(os.environ.get('TEST_PG_DSN'), 'Set TEST_PG_DSN for isolated PostgreSQL guard tests')
class DatabaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg2.connect(os.environ['TEST_PG_DSN'])
        self.addCleanup(self.conn.close)
        params = self.conn.get_dsn_parameters()
        if params.get('host') not in ('127.0.0.1', 'localhost') or not params['dbname'].endswith('_test'):
            self.fail('Database guard tests require a loopback disposable database ending in _test')
        self.cr = self.conn.cursor()
        self.addCleanup(self.conn.rollback)
        schema = 'guard_test_' + uuid.uuid4().hex
        self.cr.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        self.cr.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))
        self.cr.execute('CREATE TABLE ir_module_module (name varchar PRIMARY KEY, state varchar)')
        self.cr.execute("INSERT INTO ir_module_module VALUES ('base','installed'),('sale','installed'),('crm','uninstalled')")
        guarded_upgrade.install_guard(self.cr, ['base', 'sale'])

    def denied(self, statement):
        self.cr.execute('SAVEPOINT rejected')
        with self.assertRaises(psycopg2.Error):
            self.cr.execute(statement)
        self.cr.execute('ROLLBACK TO SAVEPOINT rejected')

    def test_module_state_guard_blocks_install_remove_delete_and_rename(self):
        for statement in [
            "UPDATE ir_module_module SET state='to install' WHERE name='crm'",
            "UPDATE ir_module_module SET state='installed' WHERE name='crm'",
            "UPDATE ir_module_module SET state='to remove' WHERE name='sale'",
            "UPDATE ir_module_module SET state='uninstalled' WHERE name='sale'",
            "UPDATE ir_module_module SET name='renamed',state='uninstalled' WHERE name='sale'",
            "DELETE FROM ir_module_module WHERE name='base'",
            "INSERT INTO ir_module_module VALUES ('new_dependency','to install')",
        ]:
            with self.subTest(statement=statement):
                self.denied(statement)

    def test_installed_upgrades_and_discovery_remain_allowed(self):
        self.cr.execute("UPDATE ir_module_module SET state='to upgrade' WHERE name='sale'")
        self.cr.execute("UPDATE ir_module_module SET state='installed' WHERE name='sale'")
        self.cr.execute("INSERT INTO ir_module_module VALUES ('optional_app','uninstalled')")
        self.assertEqual(set(guarded_upgrade.installed(self.cr)), {'base', 'sale'})

    def test_new_install_checks_actual_requested_module_states(self):
        guarded_upgrade.verify_requested_modules(self.cr, ['base', 'sale'])
        for name in ('crm', 'missing_addon'):
            with self.assertRaises(RuntimeError):
                guarded_upgrade.verify_requested_modules(self.cr, ['base', name])

    def test_business_fingerprint_detects_record_changes(self):
        self.cr.execute('CREATE TABLE sale_order (id integer, name varchar, amount_total numeric)')
        self.cr.execute("INSERT INTO sale_order VALUES (1,'CLIENT/001',125.50)")
        self.cr.execute('CREATE TABLE ir_attachment (store_fname varchar)')
        with tempfile.TemporaryDirectory() as directory:
            baseline = snapshot(self.cr, directory, 'guard_test')
            assert_unchanged(self.cr, directory, 'guard_test', baseline)
            self.cr.execute('UPDATE sale_order SET amount_total=1')
            with self.assertRaises(RuntimeError):
                assert_unchanged(self.cr, directory, 'guard_test', baseline)


if __name__ == '__main__':
    unittest.main()
