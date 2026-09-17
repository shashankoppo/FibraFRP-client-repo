import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location('compose_deploy', Path(__file__).resolve().parents[1] / 'compose_deploy.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ComposeDeploymentTests(unittest.TestCase):
    project = '/home/Client ERP/FibraFRP-client-repo/odoo-19.0'

    def metadata(self, service='deploy-prod'):
        parent = self.project.rsplit('/', 1)[0]
        return {'Config': {'Labels': {
            'com.docker.compose.project': 'existing_client_project',
            'com.docker.compose.service': service,
            'com.docker.compose.oneoff': 'True',
            'com.docker.compose.project.working_dir': self.project,
            'com.docker.compose.project.config_files': self.project + '/docker-compose.yml',
        }}, 'Mounts': [
            {'Type': 'bind', 'Source': parent, 'Destination': parent, 'RW': True},
            {'Type': 'bind', 'Source': '/var/run/docker.sock', 'Destination': '/var/run/docker.sock', 'RW': True},
        ]}

    def test_preserves_project_identity_paths_spaces_and_reviewed_revision(self):
        context = runner.deployment_context(self.metadata(), self.project, 'production')
        self.assertEqual(context['COMPOSE_PROJECT_NAME'], 'existing_client_project')
        self.assertEqual(context['COMPOSE_FILE'], self.project + '/docker-compose.yml')
        self.assertEqual(context['PWD'], self.project)
        self.assertEqual(context['NO_PULL'], 'YES')
        self.assertNotEqual(context['GIT_CONFIG_VALUE_0'], '*')

    def test_new_mode_requires_explicit_new_service(self):
        runner.deployment_context(self.metadata('deploy-new'), self.project, 'new')
        with self.assertRaises(ValueError):
            runner.deployment_context(self.metadata(), self.project, 'new')

    def test_ordinary_compose_up_never_runs_upgrade(self):
        data = self.metadata()
        data['Config']['Labels']['com.docker.compose.oneoff'] = 'False'
        with self.assertRaises(ValueError):
            runner.deployment_context(data, self.project, 'production')

    def test_refuses_renamed_missing_or_readonly_bind(self):
        for values in ({'Source': '/different/checkout'}, {'Destination': '/workspace'}, {'RW': False}, {'Type': 'volume'}):
            data = self.metadata()
            data['Mounts'][0].update(values)
            with self.assertRaises(ValueError):
                runner.deployment_context(data, self.project, 'production')

    def test_refuses_missing_local_socket(self):
        data = self.metadata()
        data['Mounts'].pop()
        with self.assertRaises(ValueError):
            runner.deployment_context(data, self.project, 'production')

    def test_refuses_changed_compose_project_directory(self):
        data = self.metadata()
        data['Config']['Labels']['com.docker.compose.project.working_dir'] = '/other/client'
        with self.assertRaises(ValueError):
            runner.deployment_context(data, self.project, 'production')

    def test_preserves_custom_compose_and_environment_files(self):
        data = self.metadata()
        labels = data['Config']['Labels']
        labels['com.docker.compose.project.config_files'] += ',' + self.project + '/client.yml'
        labels['com.docker.compose.project.environment_file'] = self.project + '/client.env'
        context = runner.deployment_context(data, self.project, 'production')
        self.assertEqual(context['COMPOSE_FILE'].split(':'), [self.project + '/docker-compose.yml', self.project + '/client.yml'])
        self.assertEqual(context['COMPOSE_ENV_FILES'], self.project + '/client.env')

    def test_refuses_missing_identity_and_external_configurations(self):
        for key, value in [('com.docker.compose.project', ''),
                           ('com.docker.compose.project.config_files', ''),
                           ('com.docker.compose.project.config_files', '/outside/client.yml'),
                           ('com.docker.compose.project.environment_file', '/outside/secrets.env'),
                           ('com.docker.compose.project.environment_file', self.project + '/secrets.txt')]:
            data = self.metadata()
            data['Config']['Labels'][key] = value
            with self.assertRaises(ValueError):
                runner.deployment_context(data, self.project, 'production')


if __name__ == '__main__':
    unittest.main()
