import copy
import importlib.util
import io
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy = load('client_deploy', ROOT / 'deploy/client_deploy.py')
privacy = load('wa_privacy', ROOT / 'custom_addons/elsx_whatsapp_marketing/privacy.py')


class DeploymentTests(unittest.TestCase):
    def config(self, **settings):
        return {'x-deployment': dict(database='Client_A', backup_passphrase='test-secret', **settings),
                'services': {'odoo': {'environment': {'DB_PASSWORD': 'isolated-test-password'}, 'volumes': []}}}

    def test_same_command_resolves_different_vps_targets(self):
        a = self.config()
        b = copy.deepcopy(a)
        b['x-deployment']['database'] = 'Client_B'
        self.assertEqual(deploy.validate_config(a, 'production'), 'Client_A')
        self.assertEqual(deploy.validate_config(b, 'production'), 'Client_B')

    def test_missing_conflicting_and_placeholder_targets_fail(self):
        for primary, alias in [('', ''), ('Client_A', 'Client_B'), ('YOUR_CLIENT_DB_NAME', ''), ("client'; DROP DATABASE postgres; --", '')]:
            with self.subTest(primary=primary):
                config = self.config()
                config['x-deployment'].update(database=primary, legacy_database=alias)
                with self.assertRaises(ValueError):
                    deploy.validate_config(config, 'production')

    def test_legacy_alias_is_accepted_without_database_argument(self):
        config = self.config()
        config['x-deployment'].update(database='', legacy_database='Existing_DB')
        self.assertEqual(deploy.validate_config(config, 'production'), 'Existing_DB')

    def test_production_installation_options_are_rejected(self):
        for key, value in [('ODOO_AUTO_INSTALL_MODULES', 'sale'), ('ODOO_AUTO_ALLOW_INSTALL', 'YES')]:
            config = self.config()
            config['services']['odoo']['environment'][key] = value
            with self.assertRaises(ValueError):
                deploy.validate_config(config, 'production')
        with self.assertRaises(ValueError):
            deploy.validate_config(self.config(install_modules='sale'), 'production')

    def test_backup_secret_is_mandatory(self):
        config = self.config()
        config['x-deployment']['backup_passphrase'] = ''
        with self.assertRaises(ValueError):
            deploy.validate_config(config, 'production')

    def test_mutable_source_mount_is_rejected(self):
        config = self.config()
        config['services']['odoo']['volumes'] = [{'type': 'bind', 'target': '/opt/odoo/custom_addons'}]
        with self.assertRaises(ValueError):
            deploy.validate_config(config, 'production')

    def test_new_environment_requires_explicit_target_and_modules(self):
        config = self.config()
        with self.assertRaises(ValueError):
            deploy.validate_config(config, 'new')
        config['x-deployment'].update(database='', new_database='Fresh_DB', install_modules='sale,elsx_client_restrictions', admin_password='test')
        self.assertEqual(deploy.validate_config(config, 'new'), 'Fresh_DB')

    def test_new_environment_rejects_conflicting_production_targets(self):
        config = self.config(new_database='Fresh_DB', install_modules='base,elsx_client_restrictions', admin_password='test')
        with self.assertRaises(ValueError):
            deploy.validate_config(config, 'new')
        config['x-deployment'].update(database='Fresh_DB', legacy_database='Client_B')
        with self.assertRaises(ValueError):
            deploy.validate_config(config, 'new')
        config['x-deployment']['legacy_database'] = 'Fresh_DB'
        self.assertEqual(deploy.validate_config(config, 'new'), 'Fresh_DB')

    def test_new_database_name_is_validated_before_starting_services(self):
        config = self.config(new_database='Fresh-DB', install_modules='base', admin_password='test')
        config['x-deployment']['database'] = ''
        with self.assertRaises(ValueError):
            deploy.validate_config(config, 'new')

    def test_permanent_new_options_do_not_request_production_installs(self):
        config = self.config(new_database='Client_A', new_install_modules='sale,elsx_client_restrictions', admin_password='test')
        self.assertEqual(deploy.validate_config(config, 'new'), 'Client_A')
        self.assertEqual(deploy.validate_config(config, 'production'), 'Client_A')

    def test_new_install_must_explicitly_include_apps_guard(self):
        config = self.config(new_database='Client_A', new_install_modules='base', admin_password='test')
        with self.assertRaisesRegex(ValueError, 'elsx_client_restrictions'):
            deploy.validate_config(config, 'new')

    def test_conflicting_new_install_options_are_refused(self):
        config = self.config(new_database='Client_A', new_install_modules='base,elsx_client_restrictions',
                             install_modules='sale,elsx_client_restrictions', admin_password='test')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            deploy.validate_config(config, 'new')

    def test_host_backup_hash_works_without_python_311_file_digest(self):
        value = b'backup contents' * 100000
        self.assertEqual(deploy.sha256_file(io.BytesIO(value)), hashlib.sha256(value).hexdigest())

    def test_fresh_environment_rejects_empty_or_default_database_password(self):
        config = self.config(new_database='Client_A', new_install_modules='base,elsx_client_restrictions', admin_password='test')
        for value in ('', 'odoo'):
            config['services']['odoo']['environment']['DB_PASSWORD'] = value
            with self.assertRaisesRegex(ValueError, 'POSTGRES_PASSWORD'):
                deploy.validate_config(config, 'new')


class PrivacyTests(unittest.TestCase):
    def test_redaction_preserves_delivery_evidence_and_original_input(self):
        value = {'access_token': 'secret', 'text': {'body': 'Private customer text'},
                 'messages': [{'id': 'wamid.123456789012345'}]}
        result = privacy.redact(value, content=True)
        self.assertEqual(result['access_token'], '[redacted]')
        self.assertEqual(result['text'], '[redacted]')
        self.assertEqual(result['messages'], value['messages'])
        self.assertEqual(value['access_token'], 'secret')

    def test_prompt_identifiers_and_bearer_tokens_are_redacted(self):
        result = privacy.redact_text('Email user@example.com phone +91 99999 00001 Bearer secret-token')
        for token in ('user@example.com', '99999', 'secret-token'):
            self.assertNotIn(token, result)

    def test_endpoint_secrets_are_removed(self):
        result = privacy.redact_url('https://user:password@example.com/path?access_token=secret&limit=10')
        self.assertNotIn('password', result)
        self.assertNotIn('=secret', result)
        self.assertIn('limit=10', result)


if __name__ == '__main__':
    unittest.main()
