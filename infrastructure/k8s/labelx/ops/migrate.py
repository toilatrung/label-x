"""Run once per full Argo sync, after backup, with the migration credential only."""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.production")
import django
django.setup()
from django.core.management import call_command
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("SELECT pg_advisory_lock(71020261017)")
try:
    call_command("migrate", interactive=False)
    call_command("provision_runtime_db_role", "labelx_runtime", password_env="RUNTIME_DB_PASSWORD")
    call_command("migrate", check=True)
finally:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(71020261017)")
print("PASS migrations and restricted runtime grants; MVP remains UNVERIFIED")
