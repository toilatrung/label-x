"""S3 startup must retry unavailable services and fail within a bounded wait."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


spec = importlib.util.spec_from_file_location(
    "prepare_s3", Path(__file__).resolve().parents[1] / "prepare-s3.py"
)
prepare_s3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare_s3)


class PrepareS3Tests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.client = Mock()
        self.client.list_buckets.return_value = {"Buckets": []}

    def sleep(self, seconds):
        self.now += seconds

    def prepare(self):
        prepare_s3.prepare(
            self.client, timeout=5, clock=lambda: self.now, sleep=self.sleep
        )

    def test_retries_startup_then_verifies_every_bucket(self):
        self.client.list_buckets.side_effect = [
            ConnectionError("gateway starting"),
            *[{"Buckets": []}] * len(prepare_s3.BUCKETS),
        ]
        self.prepare()
        self.assertEqual(self.now, 2)
        self.assertEqual(
            self.client.head_bucket.call_args_list,
            [unittest.mock.call(Bucket=bucket) for bucket in prepare_s3.BUCKETS],
        )

    def test_existing_buckets_are_verified_without_recreation(self):
        self.client.list_buckets.return_value = {
            "Buckets": [{"Name": bucket} for bucket in prepare_s3.BUCKETS]
        }
        self.prepare()
        self.client.create_bucket.assert_not_called()
        self.assertEqual(self.client.head_bucket.call_count, len(prepare_s3.BUCKETS))

    def test_unready_filer_times_out_even_when_gateway_lists_buckets(self):
        self.client.head_bucket.side_effect = ConnectionError("filer unavailable")
        with self.assertRaisesRegex(RuntimeError, "S3 readiness timed out"):
            self.prepare()
        self.assertEqual(self.now, 5)


if __name__ == "__main__":
    unittest.main()
