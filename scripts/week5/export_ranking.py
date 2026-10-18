#!/usr/bin/env python3
"""Read-only export of one LabelX run's stored ranking to CSV + manifest + ZIP.

Reads only through the public LabelX API; it never creates snapshots/runs, takes leases, records
decisions or touches CVAT.  The only non-GET request is the optional session login.

Configuration comes from the environment, with no defaults (nothing secret is ever printed,
logged or written to the manifest):

  LABELX_BASE_URL               https://host of the LabelX deployment (required)
  LABELX_SESSION_COOKIE_FILE    file (mode 0600) holding the value of the session cookie, or
  LABELX_CREDENTIALS_FILE       file (mode 0600) with JSON {"username": ..., "password": ...}

Output goes to --out-dir, which must be outside any git worktree so exported figures are never
committed by accident.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SESSION_COOKIE_NAME = "sessionid"
CSRF_COOKIE_NAME = "labelx_csrftoken"
CSRF_HEADER = "X-CSRFToken"
MAX_PAGES = 1000
CSV_COLUMNS = (
    "rank",
    "cvat_task_id",
    "cvat_job_id",
    "frame_number",
    "snapshot_frame_id",
    "file_name",
    "risk_score",
    "risk_score_source",
    "baseline_score",
    "priority",
    "reason",
    "missing_evidence",
    "issue_counts",
    "candidate_count",
    "box_count",
    "box_rank",
    "random_rank",
    "random_audit_rank",
    "cvat_url",
)


class ExportError(RuntimeError):
    """A condition that must stop the export; the message never contains secrets."""


def read_private_file(path_value: str, label: str) -> str:
    """Return a secret file's text, refusing files readable by group/others."""
    path = Path(path_value)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as error:
        raise ExportError(f"{label}: cannot read file ({error.strerror})") from None
    if mode & 0o077:
        raise ExportError(f"{label}: file mode must be 0600 (found {mode:04o})")
    return path.read_text(encoding="utf-8").strip()


def inside_git_worktree(path: Path) -> bool:
    current = path.resolve()
    return any((parent / ".git").exists() for parent in (current, *current.parents))


class Client:
    """Minimal same-origin JSON client; GET only apart from the session login."""

    def __init__(self, base_url: str) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ExportError("LABELX_BASE_URL must be an http(s) URL")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("Accept", "application/json")]

    def _cookie(self, name: str) -> str | None:
        return next((c.value for c in self.jar if c.name == name), None)

    def use_session_cookie(self, value: str) -> None:
        host = urllib.parse.urlsplit(self.origin).hostname or ""
        self.jar.set_cookie(
            http.cookiejar.Cookie(
                0, SESSION_COOKIE_NAME, value, None, False, host, True, False, "/", True,
                self.origin.startswith("https"), None, True, None, None, {},
            )
        )  # fmt: skip

    def login(self, username: str, password: str) -> None:
        self.get_json("/api/auth/csrf/", allow_empty=True)
        token = self._cookie(CSRF_COOKIE_NAME)
        if not token:
            raise ExportError("server did not set the CSRF cookie")
        body = json.dumps({"username": username, "password": password}).encode()
        request = urllib.request.Request(  # noqa: S310 - http(s) checked in __init__
            self.origin + "/api/auth/login/",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                CSRF_HEADER: token,
                "Referer": self.origin + "/",
            },
        )
        self._open(request)

    def _open(self, request: urllib.request.Request) -> bytes:
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            raise ExportError(
                f"HTTP {error.code} for {request.get_method()} {request.selector}"
            ) from None
        except urllib.error.URLError as error:
            raise ExportError(f"cannot reach server: {error.reason}") from None

    def get_json(self, path_or_url: str, *, allow_empty: bool = False) -> Any:
        url = path_or_url if "://" in path_or_url else self.origin + path_or_url
        if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(self.origin).netloc:
            raise ExportError("refusing to follow a link to another origin")
        raw = self._open(urllib.request.Request(url, method="GET"))  # noqa: S310
        if not raw and allow_empty:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ExportError(
                f"non-JSON response for GET {urllib.parse.urlsplit(url).path}"
            ) from None

    def pages(self, path: str) -> Iterator[Mapping[str, Any]]:
        url: str | None = path
        for _ in range(MAX_PAGES):
            if url is None:
                return
            page = self.get_json(url)
            yield page
            url = page.get("next")
        raise ExportError(f"pagination did not end for {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_reason(row: Mapping[str, Any]) -> str:
    """Human-readable ranking reason built only from stored explanation fields."""
    explanation = row.get("explanation") or {}
    parts = [
        f"{item.get('family')}: n={item.get('n_i')} q={item.get('q_i')} "
        f"-> {item.get('contribution')}"
        for item in explanation.get("contributions", ())
    ]
    warnings = explanation.get("structural_warnings") or ()
    if warnings:
        parts.append(f"structural_warnings={len(warnings)}")
    if row.get("missing_evidence"):
        parts.append("missing_evidence")
    if not parts:
        parts.append("no candidate contribution (baseline only)")
    return "; ".join(parts)


def snapshot_frame_index(snapshot: Mapping[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    """Map (cvat_task_id, frame_number) to the first job's frame metadata."""
    found: dict[tuple[int, int], dict[str, Any]] = {}
    for job in snapshot.get("jobs", ()):
        for frame in job.get("frames", ()):
            key = (job["cvat_task_id"], frame["frame_index"])
            entry = found.setdefault(key, {"job_ids": [], **frame})
            entry["job_ids"].append(job["cvat_job_id"])
    return found


def build_rows(
    ranked: list[Mapping[str, Any]],
    frames: Mapping[tuple[int, int], Mapping[str, Any]],
    candidate_counts: Mapping[tuple[int, int], int] | None,
    random_audit: Mapping[tuple[int, int], int],
) -> list[dict[str, Any]]:
    rows = []
    for row in ranked:
        key = (row["frame_key"]["cvat_task_id"], row["frame_key"]["frame_number"])
        frame = frames.get(key, {})
        exact = (row.get("explanation") or {}).get("score")
        rows.append(
            {
                "rank": row["rank"],
                "cvat_task_id": key[0],
                "cvat_job_id": "|".join(str(j) for j in frame.get("job_ids", ())),
                "frame_number": key[1],
                "snapshot_frame_id": row["frame_id"],
                "file_name": frame.get("file_name", ""),
                # explanation.score is the stored Decimal string; the API float may lose digits.
                "risk_score": exact if exact is not None else repr(row["score"]),
                "risk_score_source": "explanation.score" if exact is not None else "api_float",
                "baseline_score": (row.get("explanation") or {}).get(
                    "baseline_score", repr(row["baseline_score"])
                ),
                "priority": row.get("priority", ""),
                "reason": describe_reason(row),
                "missing_evidence": str(bool(row["missing_evidence"])).lower(),
                "issue_counts": json.dumps(row["issue_counts"], sort_keys=True),
                "candidate_count": "" if candidate_counts is None else candidate_counts.get(key, 0),
                "box_count": "",
                "box_rank": "",
                "random_rank": "",
                "random_audit_rank": random_audit.get(key, ""),
                "cvat_url": frame.get("cvat_url", ""),
            }
        )
    return rows


def run_export(
    client: Client, run_id: int, out_dir: Path, expect_snapshot_id: int | None
) -> dict[str, Any]:
    run = client.get_json(f"/api/runs/{run_id}/")
    snapshot_id = run["snapshot_id"]
    if expect_snapshot_id is not None and snapshot_id != expect_snapshot_id:
        raise ExportError(
            f"run {run_id} uses snapshot {snapshot_id}, expected {expect_snapshot_id}"
        )

    def ranking(queue: str) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        head: Mapping[str, Any] = {}
        for page in client.pages(f"/api/runs/{run_id}/ranking/?queue={queue}"):
            head = head or page
            rows.extend(page["results"])
        return rows, head

    risk, risk_head = ranking("risk")
    audit, audit_head = ranking("random")
    snapshot = client.get_json(f"/api/snapshots/{snapshot_id}/")
    frames = snapshot_frame_index(snapshot)

    counts: dict[tuple[int, int], int] = defaultdict(int)
    raw_count = dedup_count = None
    for page in client.pages(f"/api/runs/{run_id}/candidates/?page_size=100"):
        raw_count, dedup_count = page.get("raw_count"), page.get("dedup_count")
        for candidate in page["results"]:
            frame = candidate["frame"]
            counts[(frame["cvat_task_id"], frame["frame_number"])] += 1

    audit_rank = {
        (r["frame_key"]["cvat_task_id"], r["frame_key"]["frame_number"]): r["rank"] for r in audit
    }
    rows = build_rows(risk, frames, counts, audit_rank)
    missing_frames = [
        r["frame_key"]
        for r in risk
        if (r["frame_key"]["cvat_task_id"], r["frame_key"]["frame_number"]) not in frames
    ]

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"run{run_id}_snapshot{snapshot_id}_ranking.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "tool": {
            "script": "scripts/week5/export_ranking.py",
            "sha256": sha256_file(Path(__file__)),
        },
        "source": {
            "origin": client.origin,
            "endpoints": [
                f"GET /api/runs/{run_id}/",
                f"GET /api/runs/{run_id}/ranking/?queue=risk",
                f"GET /api/runs/{run_id}/ranking/?queue=random",
                f"GET /api/snapshots/{snapshot_id}/",
                f"GET /api/runs/{run_id}/candidates/",
            ],
        },
        "run": {
            "id": run_id,
            "status": run.get("status"),
            "is_final": run.get("is_final"),
            "seed": run.get("seed"),
            "score_version": run.get("score_version"),
        },
        "snapshot": {
            "id": snapshot_id,
            "status": snapshot.get("status"),
            "revision_hash": snapshot.get("revision_hash"),
            "jobs": sorted(
                {(j["cvat_task_id"], j["cvat_job_id"]) for j in snapshot.get("jobs", ())}
            ),
        },
        "ranking": {
            "risk_frames": len(risk),
            "risk_content_hash": risk_head.get("content_hash"),
            "risk_ranking_hash": risk_head.get("ranking_hash"),
            "random_audit_frames": len(audit),
            "random_audit_ranking_hash": audit_head.get("ranking_hash"),
            "candidates_raw": raw_count,
            "candidates_dedup": dedup_count,
        },
        "files": {csv_path.name: {"sha256": sha256_file(csv_path), "rows": len(rows)}},
        "columns_note": {
            "risk_score": "stored Decimal string from explanation.score (not rounded)",
            "random_audit_rank": (
                "rank inside the independent random-audit sample only, "
                "not a full-set random ranking"
            ),
        },
        "missing_fields": {
            "box_count / box_rank": (
                "no API exposes per-frame annotation counts "
                "or the annotation_count_control ordering"
            ),
            "random_rank": (
                "the full-set random_control ordering is stored server-side "
                "but no API exposes it; random_audit is a sample"
            ),
            "image_digest / image_version": (
                "not exposed by the API; verify through read-only Kubernetes access"
            ),
            "frames_without_snapshot_metadata": missing_frames,
        },
        "warnings": (
            [] if run.get("status") == "completed" else [f"run status is {run.get('status')!r}"]
        ),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )

    zip_path = out_dir / f"run{run_id}_snapshot{snapshot_id}_export.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (csv_path, manifest_path):
            archive.write(path, path.name)
    digest = sha256_file(zip_path)
    (out_dir / f"{zip_path.name}.sha256").write_text(
        f"{digest}  {zip_path.name}\n", encoding="utf-8"
    )
    manifest["zip"] = {"path": str(zip_path), "sha256": digest}
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--out-dir", type=Path, required=True, help="directory outside any git worktree"
    )
    parser.add_argument(
        "--expect-snapshot-id", type=int, help="abort unless the run uses this snapshot"
    )
    args = parser.parse_args(argv)

    base_url = os.environ.get("LABELX_BASE_URL")
    if not base_url:
        print("LABELX_BASE_URL is required", file=sys.stderr)
        return 2
    if inside_git_worktree(args.out_dir):
        print("--out-dir must be outside any git worktree", file=sys.stderr)
        return 2
    try:
        client = Client(base_url)
        cookie_file = os.environ.get("LABELX_SESSION_COOKIE_FILE")
        credentials_file = os.environ.get("LABELX_CREDENTIALS_FILE")
        if cookie_file:
            client.use_session_cookie(read_private_file(cookie_file, "LABELX_SESSION_COOKIE_FILE"))
        elif credentials_file:
            credentials = json.loads(read_private_file(credentials_file, "LABELX_CREDENTIALS_FILE"))
            client.login(credentials["username"], credentials["password"])
        else:
            raise ExportError("set LABELX_SESSION_COOKIE_FILE or LABELX_CREDENTIALS_FILE")
        manifest = run_export(client, args.run_id, args.out_dir, args.expect_snapshot_id)
    except (ExportError, KeyError, json.JSONDecodeError) as error:
        print(
            f"export failed: {error if isinstance(error, ExportError) else type(error).__name__}",
            file=sys.stderr,
        )
        return 1
    print(f"ZIP: {manifest['zip']['path']}")
    print(f"SHA-256: {manifest['zip']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
