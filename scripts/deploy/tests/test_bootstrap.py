"""Credential preservation and dependency failure cases; no cluster access or real secrets."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'bootstrap.py'
spec = importlib.util.spec_from_file_location('bootstrap_under_test', path)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def values(documents):
    return {item['metadata']['name']: item['stringData'] for item in documents}


class BootstrapTests(unittest.TestCase):
    def test_fresh_local_login_does_not_require_external_services(self):
        data = values(bootstrap.build_documents({'BACKUP_MODE': 'local'}, {}, set()))
        self.assertEqual(data['labelx-backup']['BACKUP_MODE'], 'local')
        self.assertNotIn('BACKUP_S3_ENDPOINT_URL', data['labelx-backup'])
        self.assertTrue(data['labelx-runtime']['DATABASE_URL'])
        self.assertNotIn('CVAT_SERVICE_TOKEN', data['labelx-runtime'])
        self.assertNotEqual(data['labelx-s3']['ADMIN_ACCESS_KEY'], data['labelx-runtime']['OBJECT_STORAGE_ACCESS_KEY'])

    def test_existing_data_without_keys_never_generates_passwords(self):
        for claim in ('labelx-postgres', 'labelx-redis', 'labelx-backups', 'labelx-s3'):
            with self.subTest(claim=claim), self.assertRaises(RuntimeError):
                bootstrap.build_documents({}, {}, {claim})

    def test_partial_secret_set_is_rejected(self):
        with self.assertRaises(RuntimeError):
            bootstrap.build_documents({}, {'labelx-postgres': {}}, set())

    def test_reapply_preserves_every_key(self):
        old = values(bootstrap.build_documents({}, {}, set()))
        current = values(bootstrap.build_documents({}, old, {'labelx-postgres', 'labelx-s3'}))
        self.assertEqual(old, current)

    def test_dependency_update_does_not_rotate_core_or_s3(self):
        old = values(bootstrap.build_documents({}, {}, set()))
        config = {'CVAT_BASE_URL': 'https://cvat.example.test', 'CVAT_SERVICE_TOKEN': 'test-only-not-a-live-token'}
        current = values(bootstrap.build_documents(config, old, {'labelx-postgres', 'labelx-s3'}, True))
        for name in ('labelx-s3', 'labelx-postgres', 'labelx-redis', 'labelx-migration', 'labelx-backup'):
            self.assertEqual(old[name], current[name])
        self.assertEqual(old['labelx-runtime']['DJANGO_SECRET_KEY'], current['labelx-runtime']['DJANGO_SECRET_KEY'])

    def test_offsite_cannot_be_missing_or_application_s3(self):
        for config in ({'BACKUP_MODE': 'offsite'}, {'CVAT_BASE_URL': 'https://cvat.example.test'}):
            with self.subTest(config=config), self.assertRaises(RuntimeError):
                bootstrap.dependency_config(config)


if __name__ == '__main__':
    unittest.main()
