#!/usr/bin/env python3
"""Smoke production images on an isolated Docker network; never uses deployment credentials."""

import argparse
import json
import subprocess
import time
import uuid


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(
            f"docker {args[0]} failed:\n{result.stdout}\n{result.stderr}"
        )
    return result


def wait_until(check, description: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(1)
    raise RuntimeError(f"Timeout: {description}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", required=True)
    parser.add_argument("--backend", required=True)
    args = parser.parse_args()
    prefix = "labelx-image-smoke-" + uuid.uuid4().hex[:12]
    containers: list[str] = []
    network_created = False

    def start(role: str, image: str, *command: str, env=()) -> str:
        name = prefix + "-" + role
        containers.append(name)
        options = [
            "run",
            "--detach",
            "--name",
            name,
            "--hostname",
            role,
            "--network",
            prefix,
            "--network-alias",
            role,
            "--label",
            "labelx.image-smoke=" + prefix,
        ]
        for item in env:
            options += ["--env", item]
        docker(*options, image, *command)
        return name

    try:
        for image in (args.frontend, args.backend):
            metadata = json.loads(docker("image", "inspect", image).stdout)[0]
            assert metadata["Architecture"] == "amd64", image
            assert metadata["Config"]["User"] not in ("", "0", "root", "0:0"), image
            forbidden = (
                "DJANGO_SECRET_KEY=",
                "DATABASE_URL=",
                "CVAT_SERVICE_TOKEN=",
                "OBJECT_STORAGE_SECRET_KEY=",
                "GPU_WORKER_CREDENTIALS=",
            )
            assert not any(
                x.startswith(forbidden) for x in metadata["Config"].get("Env", [])
            )
        docker("network", "create", "--label", "labelx.image-smoke=" + prefix, prefix)
        network_created = True
        pg_password = uuid.uuid4().hex
        runtime_password = uuid.uuid4().hex
        common = [
            "DJANGO_SECRET_KEY=" + uuid.uuid4().hex + uuid.uuid4().hex,
            "DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,api,frontend",
            "CORS_ALLOWED_ORIGINS=https://label-x.williamtrinh.online",
            "CSRF_TRUSTED_ORIGINS=https://label-x.williamtrinh.online",
            "SECURE_SSL_REDIRECT=False",  # This test network is HTTP-only.
            "CELERY_BROKER_URL=redis://redis:6379/0",
            "CELERY_RESULT_BACKEND=redis://redis:6379/1",
            "AWS_EC2_METADATA_DISABLED=true",
        ]
        owner_env = [
            *common,
            f"DATABASE_URL=postgres://labelx:{pg_password}@postgres:5432/labelx",
        ]
        runtime_env = [
            *common,
            f"DATABASE_URL=postgres://labelx_runtime:{runtime_password}@postgres:5432/labelx",
        ]
        postgres = start(
            "postgres",
            "postgres:17",
            env=[
                "POSTGRES_USER=labelx",
                "POSTGRES_PASSWORD=" + pg_password,
                "POSTGRES_DB=labelx",
            ],
        )
        redis = start("redis", "redis:7-alpine")
        wait_until(
            lambda: (
                docker(
                    "exec", postgres, "pg_isready", "-U", "labelx", check=False
                ).returncode
                == 0
            ),
            "PostgreSQL ready",
        )
        wait_until(
            lambda: (
                docker("exec", redis, "redis-cli", "ping", check=False).stdout.strip()
                == "PONG"
            ),
            "Redis ready",
        )

        def backend_command(env, *command: str) -> str:
            options = ["run", "--rm", "--network", prefix]
            for item in env:
                options += ["--env", item]
            return docker(*options, args.backend, *command).stdout

        backend_command(owner_env, "python", "manage.py", "migrate", "--noinput")
        backend_command(
            [*owner_env, "RUNTIME_DB_PASSWORD=" + runtime_password],
            "python",
            "manage.py",
            "provision_runtime_db_role",
            "labelx_runtime",
            "--password-env",
            "RUNTIME_DB_PASSWORD",
        )
        backend_command(
            runtime_env, "python", "manage.py", "check", "--deploy", "--tag", "database"
        )
        backend_command(
            runtime_env,
            "python",
            "-c",
            """
from pathlib import Path
import importlib.util
assert not list(Path('/app').glob('**/.env*'))
# uv's tiny Python path hook is not a detector checkpoint.
assert all(p.name == '_virtualenv.pth' and '.venv' in p.parts and p.stat().st_size < 1024
           for p in Path('/app').glob('**/*.pth'))
assert not list(Path('/app').glob('**/*.pt'))
assert not list(Path('/app').glob('**/*.onnx'))
assert not Path('/app/fixtures').exists()
assert not Path('/app/tests').exists()
assert importlib.util.find_spec('torch') is None
assert importlib.util.find_spec('pytest') is None
""",
        )
        print(
            "PASS backend: non-root amd64, clean image, migration and restricted runtime role",
            flush=True,
        )
        api = start("api", args.backend, env=runtime_env)
        health = "import urllib.request; assert urllib.request.urlopen('http://localhost:8000/healthz/').status == 200"
        wait_until(
            lambda: (
                docker("exec", api, "python", "-c", health, check=False).returncode == 0
            ),
            "Gunicorn liveness",
        )
        backend_command(
            runtime_env,
            "python",
            "-c",
            """
import urllib.request
for path in ('/healthz/', '/static/admin/css/base.css', '/admin/login/'):
    response = urllib.request.urlopen('http://api:8000' + path)
    assert response.status == 200, path
""",
        )
        worker = start(
            "worker",
            args.backend,
            "celery",
            "-A",
            "config",
            "worker",
            "-l",
            "INFO",
            "--concurrency=1",
            "--max-tasks-per-child=20",
            "--max-memory-per-child=393216",
            "--hostname=smoke@worker",
            env=runtime_env,
        )
        wait_until(
            lambda: (
                docker(
                    "exec",
                    worker,
                    "celery",
                    "-A",
                    "config",
                    "inspect",
                    "ping",
                    "--destination",
                    "smoke@worker",
                    "--timeout=2",
                    check=False,
                ).returncode
                == 0
            ),
            "CPU worker ping",
        )
        beat = start(
            "beat",
            args.backend,
            "celery",
            "-A",
            "config",
            "beat",
            "-l",
            "INFO",
            "--pidfile=/tmp/celerybeat.pid",
            "--schedule=/tmp/celerybeat-schedule",
            env=runtime_env,
        )
        wait_until(
            lambda: "beat: Starting" in docker("logs", beat).stderr,
            "Celery beat startup",
        )
        time.sleep(2)
        assert (
            docker("inspect", "--format", "{{.State.Running}}", beat).stdout.strip()
            == "true"
        )
        assert "Traceback" not in docker("logs", beat).stderr
        print(
            "PASS backend: Gunicorn, liveness, admin/static, CPU worker and beat",
            flush=True,
        )

        frontend = start(
            "frontend",
            args.frontend,
            env=[
                "LABELX_API_PROXY_TARGET=http://api:8000",  # Differs from the build/default target.
                "NEXT_PUBLIC_AUTH_MODE=mock",  # Production must still proxy to real Django.
            ],
        )
        ping = "fetch('http://localhost:3000/login').then(r=>process.exit(r.status===200?0:1)).catch(()=>process.exit(1))"
        wait_until(
            lambda: (
                docker("exec", frontend, "node", "-e", ping, check=False).returncode
                == 0
            ),
            "standalone Next.js",
        )
        docker(
            "exec",
            frontend,
            "node",
            "-e",
            r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  assert(!fs.existsSync('/app/.env'));
  assert(!fs.existsSync('/app/.env.local'));
  assert(!fs.existsSync('/app/public/samples'));
  const base = 'http://localhost:3000';
  const login = await fetch(base + '/login');
  assert.equal(login.status, 200);
  const html = await login.text();
  const asset = html.match(/(?:src|href)="([^"<>]*\/_next\/static\/[^"<>]+)"/);
  assert(asset, 'Next.js static asset in rendered page');
  assert.equal((await fetch(new URL(asset[1].replaceAll('&amp;', '&'), base))).status, 200);
  assert.equal((await fetch(base + '/labelx-logo.png')).status, 200);
  for (const path of ['/api/auth/csrf', '/api/auth/csrf/']) {
    const response = await fetch(base + path, {redirect: 'manual', headers: {'X-Forwarded-Proto': 'https'}});
    assert.equal(response.status, 204, path);
    assert((response.headers.get('set-cookie') || '').includes('labelx_csrftoken='));
    assert((response.headers.get('set-cookie') || '').toLowerCase().includes('secure'));
    assert((response.headers.get('strict-transport-security') || '').includes('max-age='));
  }
  const csrf = await fetch(base + '/api/auth/csrf/');
  const cookie = csrf.headers.get('set-cookie').match(/labelx_csrftoken=([^;]+)/)[1];
  const rejectedLogin = await fetch(base + '/api/auth/login', {
    method: 'POST', redirect: 'manual',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': cookie,
      Cookie: `labelx_csrftoken=${cookie}`, Origin: 'https://label-x.williamtrinh.online',
      'X-Forwarded-Proto': 'https'},
    body: JSON.stringify({username: 'nonexistent-smoke-user', password: 'smoke-only'}),
  });
  assert.equal(rejectedLogin.status, 400, 'POST body/method must reach Django without a redirect');
  assert.equal((await rejectedLogin.json()).code, 'INVALID_CREDENTIALS');
  const admin = await fetch(base + '/admin/login/', {redirect: 'manual'});
  assert.equal(admin.status, 200);
  const adminHtml = await admin.text();
  const css = adminHtml.match(/href="(\/static\/admin\/css\/base\.[^"<>]+\.css)"/);
  assert(css, 'Django manifest static URL');
  const stylesheet = await fetch(base + css[1]);
  assert.equal(stylesheet.status, 200);
  assert((stylesheet.headers.get('cache-control') || '').includes('immutable'));
  assert.equal((await fetch(base + '/api/auth/mock-users/')).status, 404);
  console.log('PASS frontend: standalone, assets, runtime proxy, cookies, admin/static and no mock auth');
})().catch(error => { console.error(error); process.exit(1); });
""",
        )
        print(
            "PASS frontend: standalone, assets, runtime proxy, cookies, admin/static and no mock auth",
            flush=True,
        )
    except BaseException:
        for name in containers:
            logs = docker("logs", "--tail", "35", name, check=False)
            print(f"--- {name} ---\n{logs.stdout}\n{logs.stderr}", flush=True)
        raise
    finally:
        for name in reversed(containers):
            docker("rm", "--force", "--volumes", name, check=False)
        if network_created:
            docker("network", "rm", prefix, check=False)


if __name__ == "__main__":
    main()
