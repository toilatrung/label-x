"""Safety checks for isolated-service probe without live infrastructure."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('evaluation_probe', Path(__file__).parents[1] / 'evaluation-probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class EvaluationProbeTests(unittest.TestCase):
    def environment(self):
        return dict(LABELX_EVALUATION_ISOLATED='true', LABELX_TEST_NAMESPACE='ci-123-1',
                    DATABASE_URL='postgres://secret', CELERY_BROKER_URL='redis://secret',
                    CELERY_RESULT_BACKEND='redis://secret', OBJECT_STORAGE_ENDPOINT_URL='http://secret',
                    OBJECT_STORAGE_ACCESS_KEY='private-access', OBJECT_STORAGE_SECRET_KEY='private-secret',
                    OBJECT_STORAGE_BUCKET='test-bucket')

    def test_refuses_unacknowledged_or_unsafe_namespace_before_connections(self):
        for changes in ({'LABELX_EVALUATION_ISOLATED': 'false'}, {'LABELX_TEST_NAMESPACE': '../production'}):
            with self.subTest(changes=changes), patch.object(probe, 'database') as database:
                with self.assertRaises(ValueError):
                    probe.run(self.environment() | changes)
                database.assert_not_called()

    def test_failures_are_redacted_and_other_services_still_checked(self):
        with patch.object(probe, 'database', side_effect=RuntimeError('private-secret postgres://secret')), \
             patch.object(probe, 'redis_service') as redis, patch.object(probe, 'storage'):
            result = probe.run(self.environment())
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['checks']['postgres'], 'FAIL')
        self.assertEqual(redis.call_count, 2)
        self.assertNotIn('secret', str(result))


if __name__ == '__main__':
    unittest.main()
