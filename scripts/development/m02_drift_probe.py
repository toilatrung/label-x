#!/usr/bin/env python3
"""AC-03 trên CVAT thật: drift giữa hai lần đọc, snapshot khóa bất biến, lineage.

Tạo project/task THỬ NGHIỆM riêng (không đụng dữ liệu learner của dataset chính) bằng token
provisioner (chỉ công cụ dev). Đường sản phẩm (create_snapshot_from_cvat) chỉ dùng token đọc.
Chạy: CVAT_PROVISIONER_TOKEN=... uv run --project src/backend python scripts/development/m02_drift_probe.py \
  --images DIR --manifest .cache/cvat/t019-learner-bdd100k.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
import httpx  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from cvat_adapter.client import CvatReadClient  # noqa: E402
from django.conf import settings  # noqa: E402
from snapshots.models import Snapshot  # noqa: E402
from snapshots.orchestration import SnapshotScope, create_snapshot_from_cvat  # noqa: E402


class Prov:
    def __init__(self, base: str, token: str) -> None:
        self.c = httpx.Client(base_url=base + "/api", headers={"Authorization": f"Bearer {token}"}, timeout=120)

    def j(self, method: str, path: str, **kw):  # noqa: ANN001, ANN201
        r = self.c.request(method, path, **kw)
        r.raise_for_status()
        return r.json() if r.content else None


def build(prov: Prov, images: Path, manifest: dict, stamp: str) -> tuple[int, int, int, dict[str, int]]:
    labels = [{"name": x["name"], "type": "rectangle", "color": x["color"]} for x in manifest["labels"]]
    project = prov.j("POST", "/projects", json={"name": f"labelx-drift-probe-{stamp}", "labels": labels})
    task = prov.j("POST", "/tasks", json={"name": f"drift-probe-{stamp}", "project_id": project["id"]})
    picked = manifest["images"][:3]
    files = [("client_files[%d]" % i, (Path(x["file_name"]).name, (images / Path(x["file_name"]).name).read_bytes(), "image/jpeg")) for i, x in enumerate(picked)]
    r = prov.c.post(f"/tasks/{task['id']}/data", data={"image_quality": "70"}, files=files)
    r.raise_for_status()
    for _ in range(90):
        t = prov.j("GET", f"/tasks/{task['id']}")
        jobs = prov.j("GET", "/jobs", params={"task_id": task["id"]})["results"]
        if t.get("size") == 3 and jobs:
            break
        time.sleep(2)
    else:
        raise TimeoutError("task chưa sẵn sàng")
    job_id = jobs[0]["id"]
    ids = {x["name"]: x["id"] for x in prov.j("GET", "/labels", params={"project_id": project["id"]})["results"]}
    return project["id"], task["id"], job_id, ids


def put_annotations(prov: Prov, job_id: int, label_ids: dict[str, int], picked: list[dict], extra: bool) -> None:
    shapes = []
    for frame, img in enumerate(picked):
        for ann in img["annotations"][:2]:
            x1, y1, x2, y2 = ann["bbox"]
            shapes.append({"type": "rectangle", "frame": frame, "label_id": label_ids[ann["label"]],
                           "points": [x1, y1, x2, y2], "occluded": False, "outside": False, "z_order": 0,
                           "rotation": 0, "attributes": [], "source": "manual"})
    if extra:
        shapes.append({"type": "rectangle", "frame": 0, "label_id": label_ids["car"], "points": [10, 10, 60, 60],
                       "occluded": False, "outside": False, "z_order": 0, "rotation": 0, "attributes": [], "source": "manual"})
    prov.j("PUT", f"/jobs/{job_id}/annotations", json={"version": 0, "tags": [], "shapes": shapes, "tracks": []})


class MutatingClient(CvatReadClient):
    """Đọc thật; sau lần đọc annotation đầu tiên thì gọi hook ghi (mô phỏng người dùng sửa giữa chừng)."""

    hook = None

    def get_job_annotations(self, job_id: int):  # noqa: ANN201
        data = super().get_job_annotations(job_id)
        if self.hook is not None:
            hook, self.hook = self.hook, None
            hook()
        return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    prov = Prov(settings.CVAT_BASE_URL, os.environ["CVAT_PROVISIONER_TOKEN"])
    manifest = json.loads(a.manifest.read_text())
    stamp = str(int(time.time()))
    project_id, task_id, job_id, label_ids = build(prov, a.images, manifest, stamp)
    picked = manifest["images"][:3]
    put_annotations(prov, job_id, label_ids, picked, extra=False)
    user = get_user_model().objects.get(username="e2e_qa_lead")
    scope = SnapshotScope(cvat_task_ids=[], cvat_job_ids=[])
    res: dict[str, object] = {"project_id": project_id, "task_id": task_id, "job_id": job_id}

    def snap(key: str, client: CvatReadClient) -> Snapshot:
        return create_snapshot_from_cvat(dataset_id=project_id, scope=scope, note=key, created_by=user,
                                         idempotency_key=f"probe-{stamp}-{key}", client=client)

    base_client = lambda: CvatReadClient(settings.CVAT_BASE_URL, settings.CVAT_SERVICE_TOKEN)  # noqa: E731
    mc = MutatingClient(settings.CVAT_BASE_URL, settings.CVAT_SERVICE_TOKEN)
    mc.hook = lambda: put_annotations(prov, job_id, label_ids, picked, extra=True)  # đổi giữa hai lần đọc
    drift = snap("drift", mc)
    res["drift"] = {"status": drift.status, "drift_jobs": drift.drift_jobs if hasattr(drift, "drift_jobs") else None,
                    "reason": drift.failure_reason, "locked": drift.status == "locked"}
    c1 = base_client()
    s1 = snap("s1", c1)
    res["s1"] = {"id": s1.pk, "status": s1.status, "revision_sha256": s1.revision_sha256, "parent": s1.parent_snapshot_id}
    c2 = base_client()
    s1b = snap("s1b", c2)  # cùng dữ liệu không đổi -> cùng revision_sha256
    res["s1b"] = {"id": s1b.pk, "status": s1b.status, "revision_sha256": s1b.revision_sha256, "parent": s1b.parent_snapshot_id}
    put_annotations(prov, job_id, label_ids, picked, extra=True)  # sửa sau khi đã khóa
    s1.refresh_from_db()
    res["s1_after_cvat_edit"] = {"revision_sha256": s1.revision_sha256, "status": s1.status}
    s2 = snap("s2", base_client())
    res["s2"] = {"id": s2.pk, "status": s2.status, "revision_sha256": s2.revision_sha256, "parent": s2.parent_snapshot_id}
    res["ok"] = (
        drift.status != "locked"
        and s1.status == "locked"
        and s1.revision_sha256 == s1b.revision_sha256
        and s2.revision_sha256 != s1.revision_sha256
        and s2.parent_snapshot_id == s1b.pk
    )
    a.out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
