"""Week-5 ranking export against a local fake server.

All payloads below are synthetic fixtures, not LabelX data or real figures.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import threading
import zipfile
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts/week5/export_ranking.py"
spec = importlib.util.spec_from_file_location("export_ranking", SCRIPT)
export_ranking = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_ranking)

PASSWORD = "fixture-password-not-real"
SESSION = "fixture-session-not-real"
EXACT = "0.123456789012345678901234567890"


def ranked(rank, frame, score="1", missing=False, contributions=()):
    return {
        "frame_id": 100 + frame,
        "frame_key": {"cvat_task_id": 13, "frame_number": frame},
        "rank": rank,
        "score": float(score),
        "baseline_score": 0.5,
        "score_version": "score_v0",
        "queue": "risk",
        "source": "risk",
        "review_state": "pending",
        "missing_evidence": missing,
        "issue_counts": {"E3": len(contributions)},
        "explanation": {
            "score": score,
            "baseline_score": "0.5",
            "contributions": list(contributions),
        },
        "lease_holder_user_id": None,
        "priority": "high",
        "thumbnail_url": "https://signed.invalid/?X-Amz-Signature=secret",
    }


CONTRIB = {"family": "E3", "n_i": 2, "q_i": "0.5", "contribution": "1.0"}
PAGE1 = [ranked(1, 3, EXACT, contributions=[CONTRIB]), ranked(2, 5, "0.9", missing=True)]
PAGE2 = [ranked(3, 0, "0.1")]
FRAMES = [
    {"id": 100 + i, "frame_index": i, "file_name": f"img{i}.jpg", "width": 1, "height": 1,
     "cvat_url": f"https://cvat.example/tasks/13/jobs/4?frame={i}"}
    for i in range(10)
]  # fmt: skip


class Handler(BaseHTTPRequestHandler):
    seen: list[tuple[str, str]] = []
    cross_origin_next = False

    def log_message(self, *args):  # silence
        pass

    def _send(self, body, status=200, headers=()):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def _authed(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        return "sessionid" in cookies and cookies["sessionid"].value == SESSION

    def do_POST(self):
        type(self).seen.append(("POST", self.path))
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        csrf = SimpleCookie(self.headers.get("Cookie", ""))
        ok = (
            self.path == "/api/auth/login/"
            and body["password"] == PASSWORD
            and self.headers.get("X-CSRFToken") == csrf["labelx_csrftoken"].value
        )
        if not ok:
            return self._send({}, 403)
        self._send({}, 200, [("Set-Cookie", f"sessionid={SESSION}; Path=/")])

    def do_GET(self):
        type(self).seen.append(("GET", self.path))
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == "/api/auth/csrf/":
            return self._send({}, 200, [("Set-Cookie", "labelx_csrftoken=tok; Path=/")])
        if not self._authed():
            return self._send({}, 403)
        host = f"http://{self.headers['Host']}"
        if url.path == "/api/runs/5/":
            return self._send(
                {
                    "id": 5,
                    "snapshot_id": 4,
                    "status": "completed",
                    "is_final": True,
                    "seed": 1,
                    "score_version": "score_v0",
                }
            )
        if url.path == "/api/runs/5/ranking/":
            head = {
                "source": "risk",
                "content_hash": "c" * 64,
                "ranking_hash": "r" * 64,
                "previous": None,
            }
            if query["queue"] == ["random"]:
                return self._send(
                    {**head, "source": "random_audit", "next": None, "results": [ranked(1, 5)]}
                )
            if "cursor" not in query:
                nxt = (
                    "https://elsewhere.invalid/x"
                    if type(self).cross_origin_next
                    else f"{host}{url.path}?queue=risk&cursor=2"
                )
                return self._send({**head, "next": nxt, "results": PAGE1})
            return self._send({**head, "next": None, "results": PAGE2})
        if url.path == "/api/snapshots/4/":
            return self._send(
                {
                    "id": 4,
                    "status": "locked",
                    "revision_hash": "sha256:abc",
                    "jobs": [{"cvat_job_id": 4, "cvat_task_id": 13, "frames": FRAMES}],
                }
            )
        if url.path == "/api/runs/5/candidates/":
            cand = {"frame": {"cvat_task_id": 13, "frame_number": 3}}
            return self._send(
                {"next": None, "raw_count": 3, "dedup_count": 2, "results": [cand, cand]}
            )
        self._send({}, 404)


@pytest.fixture
def server():
    Handler.seen = []
    Handler.cross_origin_next = False
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def secret_file(tmp_path, name, text, mode=0o600):
    path = tmp_path / name
    path.write_text(text)
    path.chmod(mode)
    return path


def run_cli(monkeypatch, tmp_path, base, *extra, creds=True):
    monkeypatch.setenv("LABELX_BASE_URL", base)
    monkeypatch.delenv("LABELX_SESSION_COOKIE_FILE", raising=False)
    monkeypatch.delenv("LABELX_CREDENTIALS_FILE", raising=False)
    if creds:
        path = secret_file(
            tmp_path, "creds.json", json.dumps({"username": "u", "password": PASSWORD})
        )
        monkeypatch.setenv("LABELX_CREDENTIALS_FILE", str(path))
    out = tmp_path / "out"
    code = export_ranking.main(["--run-id", "5", "--out-dir", str(out), *extra])
    return code, out


def test_export_writes_exact_scores_metadata_manifest_and_zip(
    monkeypatch, tmp_path, server, capsys
):
    code, out = run_cli(monkeypatch, tmp_path, server, "--expect-snapshot-id", "4")
    assert code == 0
    rows = list(csv.DictReader((out / "run5_snapshot4_ranking.csv").open(encoding="utf-8")))
    assert [r["rank"] for r in rows] == ["1", "2", "3"]
    first = rows[0]
    assert first["risk_score"] == EXACT and first["risk_score_source"] == "explanation.score"
    assert (first["cvat_task_id"], first["cvat_job_id"], first["frame_number"]) == ("13", "4", "3")
    assert first["file_name"] == "img3.jpg" and first["cvat_url"].endswith("jobs/4?frame=3")
    assert first["candidate_count"] == "2" and rows[2]["candidate_count"] == "0"
    assert "E3: n=2 q=0.5 -> 1.0" in first["reason"] and "missing_evidence" in rows[1]["reason"]
    assert rows[1]["missing_evidence"] == "true" and rows[1]["random_audit_rank"] == "1"
    assert all(r["box_count"] == r["box_rank"] == r["random_rank"] == "" for r in rows)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["run"]["id"], manifest["snapshot"]["id"]) == (5, 4)
    assert (
        manifest["ranking"]["risk_frames"] == 3 and manifest["ranking"]["random_audit_frames"] == 1
    )
    assert {"box_count / box_rank", "random_rank", "image_digest / image_version"} <= set(
        manifest["missing_fields"]
    )
    assert manifest["files"]["run5_snapshot4_ranking.csv"]["sha256"]

    zip_path = out / "run5_snapshot4_export.zip"
    stdout = capsys.readouterr().out
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    assert digest in stdout and digest in (out / "run5_snapshot4_export.zip.sha256").read_text()
    with zipfile.ZipFile(zip_path) as archive:
        assert sorted(archive.namelist()) == ["manifest.json", "run5_snapshot4_ranking.csv"]
        blob = b"".join(archive.read(n) for n in archive.namelist())
    for secret in (PASSWORD, SESSION, "X-Amz-Signature", "signed.invalid"):
        assert secret.encode() not in blob and secret not in stdout
    assert [m for m, _ in Handler.seen if m != "GET"] == ["POST"]  # only the session login writes


def test_session_cookie_file_needs_no_login_post(monkeypatch, tmp_path, server):
    monkeypatch.setenv("LABELX_SESSION_COOKIE_FILE", str(secret_file(tmp_path, "c", SESSION)))
    monkeypatch.setenv("LABELX_BASE_URL", server)
    monkeypatch.delenv("LABELX_CREDENTIALS_FILE", raising=False)
    assert export_ranking.main(["--run-id", "5", "--out-dir", str(tmp_path / "o")]) == 0
    assert {m for m, _ in Handler.seen} == {"GET"}


def test_refuses_world_readable_secret_file(monkeypatch, tmp_path, server, capsys):
    path = secret_file(tmp_path, "c", SESSION, mode=0o644)
    monkeypatch.setenv("LABELX_SESSION_COOKIE_FILE", str(path))
    monkeypatch.setenv("LABELX_BASE_URL", server)
    assert export_ranking.main(["--run-id", "5", "--out-dir", str(tmp_path / "o")]) == 1
    assert "0600" in capsys.readouterr().err and Handler.seen == []


def test_requires_explicit_base_url_and_out_dir_outside_git(monkeypatch, tmp_path, server, capsys):
    monkeypatch.delenv("LABELX_BASE_URL", raising=False)
    assert export_ranking.main(["--run-id", "5", "--out-dir", str(tmp_path / "o")]) == 2
    monkeypatch.setenv("LABELX_BASE_URL", server)
    assert export_ranking.main(["--run-id", "5", "--out-dir", str(SCRIPT.parent / "out")]) == 2
    assert "outside any git worktree" in capsys.readouterr().err


def test_wrong_snapshot_wrong_password_and_cross_origin_next_fail_closed(
    monkeypatch, tmp_path, server, capsys
):
    code, out = run_cli(monkeypatch, tmp_path, server, "--expect-snapshot-id", "9")
    assert code == 1 and not out.exists() and "expected 9" in capsys.readouterr().err
    bad = secret_file(tmp_path, "bad.json", json.dumps({"username": "u", "password": "wrong"}))
    monkeypatch.setenv("LABELX_CREDENTIALS_FILE", str(bad))
    assert export_ranking.main(["--run-id", "5", "--out-dir", str(tmp_path / "o2")]) == 1
    assert "wrong" not in capsys.readouterr().err
    Handler.cross_origin_next = True
    code, _ = run_cli(monkeypatch, tmp_path, server)
    assert code == 1 and "another origin" in capsys.readouterr().err
