"""Manage isolated test database labelx_t046_browser for T-046 browser E2E testing.
Strictly ensures no write operations ever hit the develop database 'labelx'.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import psycopg

EXPECTED_DB = "labelx_t046_browser"

print(f"=== TARGET TEST DATABASE: {EXPECTED_DB} ===")

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src" / "backend"

admin_conn = psycopg.connect("postgres://labelx:labelx@localhost:5432/postgres", autocommit=True)
with admin_conn.cursor() as cur:
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (EXPECTED_DB,))
    cur.execute(f"DROP DATABASE IF EXISTS {EXPECTED_DB}")
    print(f"Dropped previous {EXPECTED_DB} if existed.")
    cur.execute(f"CREATE DATABASE {EXPECTED_DB} OWNER labelx")
    print(f"Created fresh isolated database: {EXPECTED_DB}")
admin_conn.close()

env = os.environ.copy()
env["DATABASE_URL"] = f"postgres://labelx:labelx@localhost:5432/{EXPECTED_DB}"
env["DJANGO_SETTINGS_MODULE"] = "config.settings"

print(f"Running Django migrations against isolated database: {EXPECTED_DB}")
result = subprocess.run(
    ["uv", "run", "--frozen", "python", "manage.py", "migrate", "--noinput"],
    cwd=str(BACKEND),
    env=env,
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print(f"Migration failed:\n{result.stderr}", file=sys.stderr)
    sys.exit(result.returncode)

print(f"Successfully migrated isolated database: {EXPECTED_DB}")
