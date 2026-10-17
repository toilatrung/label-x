"""Synthetic receipts exercise rejection paths; they are never deployment manifests."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("preflight", ROOT / "infrastructure/k8s/labelx/ops/preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class ReleasePreflightTests(unittest.TestCase):
    def setUp(self):
        self.before = json.loads((ROOT / "infrastructure/k8s/labelx/kustomization.yaml").read_text())
        source_sha = hashlib.sha1(b"synthetic-test-source", usedforsecurity=False).hexdigest()
        self.receipt = {"source_sha": source_sha, "deployment_policy": "CR-120", "mvp_acceptance": "unverified", "images": {}}
        self.after = copy.deepcopy(self.before)
        self.after["images"] = []
        for component in ("backend", "frontend"):
            repository = "ghcr.io/toilatrung/labelx-" + component
            digest = "sha256:" + hashlib.sha256(("test-fixture-" + component).encode()).hexdigest()
            self.receipt["images"][component] = {"repository": repository, "digest": digest,
                "reference": repository + "@" + digest, "tag": "sha-" + source_sha}
            self.after["images"].append({"name": "labelx-" + component, "newName": repository, "digest": digest})
        for entry in self.after["configMapGenerator"]:
            if entry["name"] == "labelx-release":
                entry["literals"] = ["SOURCE_SHA=" + source_sha, "MVP_EVIDENCE=unverified", "DEPLOYMENT_POLICY=CR-120"]

    def verify(self, files=None):
        preflight.verified_transition(self.before, self.after, self.receipt,
            list(preflight.FILES) if files is None else files)

    def test_receipt_only_transition_is_eligible(self):
        self.verify()

    def test_initial_or_config_commit_waits_for_publication(self):
        for files in ([], list(preflight.FILES) + [preflight.ROOT + "applications.yaml"], ["src/backend/config/settings.py"]):
            with self.subTest(files=files), self.assertRaises(RuntimeError):
                self.verify(files)

    def test_cannot_smuggle_namespace_or_config_change_into_digest_pr(self):
        self.after["namespace"] = "other"
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_mixed_sha_pair_is_rejected(self):
        self.receipt["images"]["frontend"]["tag"] = "sha-" + hashlib.sha1(b"other", usedforsecurity=False).hexdigest()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_missing_digest_or_claimed_mvp_pass_is_rejected(self):
        self.receipt["mvp_acceptance"] = "passed"
        with self.assertRaises(RuntimeError):
            self.verify()
        self.receipt["mvp_acceptance"] = "unverified"
        self.receipt["images"]["backend"]["digest"] = "latest"
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
