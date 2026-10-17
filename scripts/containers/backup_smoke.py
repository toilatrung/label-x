#!/usr/bin/env python3
"""Exercise the actual backup/remote verification/restore scripts on isolated Docker services."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import uuid

from smoke import docker, wait_until

PG = "postgres:17@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3"
S3 = "chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d"
ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--mode", choices=["local", "offsite"], default="offsite")
    args = parser.parse_args()
    prefix = "labelx-backup-smoke-" + uuid.uuid4().hex[:10]
    names, volumes = [], []
    password, access, secret = [uuid.uuid4().hex for _ in range(3)]
    operations = str(ROOT / "infrastructure/k8s/labelx/ops")

    def container(role, image, *command, env=(), mounts=(), detach=True, user=None):
        name = prefix + "-" + role
        names.append(name)
        options = ["run", "--name", name, "--network", prefix, "--network-alias", role]
        if detach:
            options.append("--detach")
        if user:
            options += ["--user", user]
        for value in env:
            options += ["--env", value]
        for mount in mounts:
            options += ["--volume", mount]
        return docker(*options, image, *command)

    try:
        docker("network", "create", prefix)
        with tempfile.TemporaryDirectory(prefix=prefix) as directory:
            config = Path(directory, "s3.json")
            config.write_text(json.dumps({"identities": [{"name": "backup-test", "credentials": [
                {"accessKey": access, "secretKey": secret}], "actions": ["Admin", "Read", "Write", "List", "Tagging"]}]}))
            config.chmod(0o644)
            container("postgres", PG, env=["POSTGRES_USER=labelx_owner", "POSTGRES_DB=labelx", "POSTGRES_PASSWORD=" + password])
            container("s3", S3, "server", "-dir=/data", "-s3", "-s3.port=9000", "-s3.config=/etc/s3.json",
                "-master.volumeSizeLimitMB=64", mounts=[f"{config}:/etc/s3.json:ro"])
            wait_until(lambda: docker("exec", prefix + "-postgres", "pg_isready", "-U", "labelx_owner", check=False).returncode == 0, "isolated postgres")
            wait_until(lambda: docker("run", "--rm", "--network", prefix, args.backend, "python", "-c",
                "import urllib.request; urllib.request.urlopen('http://s3:9333/cluster/status',timeout=2)",
                check=False).returncode == 0, "isolated S3")
            for bucket in ("test-snapshots", "test-evidence", "test-reports", "test-backups"):
                result = subprocess.run(["docker", "exec", "-i", prefix + "-s3", "weed", "shell", "-master=localhost:9333"],
                    input=f"s3.bucket.create -name {bucket}\n", capture_output=True, text=True)
                if result.returncode:
                    raise RuntimeError("Could not create isolated S3 bucket")
            env = ["PYTHONPATH=/app", "DJANGO_SECRET_KEY=" + uuid.uuid4().hex * 2, "DJANGO_ALLOWED_HOSTS=localhost,postgres",
                "DJANGO_DEBUG=False", f"DATABASE_URL=postgres://labelx_owner:{password}@postgres:5432/labelx",
                "RUNTIME_DB_PASSWORD=" + uuid.uuid4().hex,
                "SOURCE_SHA=" + "a" * 40, "POD_NAME=" + prefix, "OBJECT_STORAGE_ENDPOINT_URL=http://s3:9000",
                "OBJECT_STORAGE_ACCESS_KEY=" + access, "OBJECT_STORAGE_SECRET_KEY=" + secret,
                "OBJECT_STORAGE_REGION=us-east-1", "OBJECT_STORAGE_BUCKET_SNAPSHOTS=test-snapshots",
                "OBJECT_STORAGE_BUCKET=test-evidence",
                "OBJECT_STORAGE_BUCKET_EVIDENCE=test-evidence", "OBJECT_STORAGE_BUCKET_REPORTS=test-reports",
                "BACKUP_S3_ENDPOINT_URL=http://s3:9000", "BACKUP_S3_ACCESS_KEY=" + access,
                "BACKUP_S3_SECRET_KEY=" + secret, "BACKUP_S3_REGION=us-east-1", "BACKUP_S3_BUCKET=test-backups",
                "BACKUP_ENCRYPTION_KEY=" + uuid.uuid4().hex * 2, "PGHOST=postgres", "PGDATABASE=labelx",
                "PGUSER=labelx_owner", "PGPASSWORD=" + password]
            env.append("BACKUP_MODE=" + args.mode)
            if args.mode == "local":
                env = [value for value in env if not value.startswith("BACKUP_S3_")]
            container("migrate", args.backend, "python", "/ops/migrate.py", env=env,
                mounts=[f"{operations}:/ops:ro"], detach=False)
            container("seed", args.backend, "python", "-c", """
import boto3,os
c=boto3.client('s3',endpoint_url=os.environ['OBJECT_STORAGE_ENDPOINT_URL'],aws_access_key_id=os.environ['OBJECT_STORAGE_ACCESS_KEY'],aws_secret_access_key=os.environ['OBJECT_STORAGE_SECRET_KEY'])
for bucket in ('test-snapshots','test-evidence','test-reports'):
 c.put_object(Bucket=bucket,Key='smoke/sample',Body=('sample-'+bucket).encode())
""", env=env, detach=False)
            for role in ("work", "backups"):
                volume = prefix + "-" + role
                volumes.append(volume)
                docker("volume", "create", volume)
                container("permissions-" + role, args.backend, "sh", "-c", "chown 10001:10001 /data", user="0",
                    mounts=[volume + ":/data"], detach=False)
            mounts = [f"{operations}:/ops:ro", prefix + "-work:/work", prefix + "-backups:/backups"]
            container("dump", PG, "sh", "/ops/backup.sh", env=env, mounts=mounts, user="10001:10001")
            container("upload", args.backend, "python", "/ops/backup-upload.py", env=env, mounts=mounts)
            for role in ("dump", "upload"):
                result = docker("wait", prefix + "-" + role)
                if result.stdout.strip() != "0":
                    raise RuntimeError("Backup smoke container failed: " + role)
                print(docker("logs", prefix + "-" + role).stdout.strip())
            container("verify", args.backend, "python", "-c", """
import boto3,hashlib,json,os
from pathlib import Path
if os.environ['BACKUP_MODE']=='local':
 receipts=list(Path('/backups/local/labelx/receipts').glob('*.json')); assert len(receipts)==1
 r=json.loads(receipts[0].read_text())
 def read(key): return (Path('/backups/local')/key).read_bytes()
else:
 c=boto3.client('s3',endpoint_url=os.environ['BACKUP_S3_ENDPOINT_URL'],aws_access_key_id=os.environ['BACKUP_S3_ACCESS_KEY'],aws_secret_access_key=os.environ['BACKUP_S3_SECRET_KEY'])
 items=c.list_objects_v2(Bucket='test-backups',Prefix='labelx/receipts/')['Contents']; assert len(items)==1
 r=json.loads(c.get_object(Bucket='test-backups',Key=items[0]['Key'])['Body'].read())
 def read(key): return c.get_object(Bucket='test-backups',Key=key)['Body'].read()
assert r['location']==os.environ['BACKUP_MODE'] and r['disaster_recovery']=='unverified'
assert r['database_restore']=='passed_disposable_database'
assert len(r['objects'])==3
for item in r['objects']:
 data=read(item['backup_key'])
 assert hashlib.sha256(data).hexdigest()==item['sha256']
assert r['mvp_acceptance']=='unverified'
print('PASS completed backup receipt and all three object checksums')
""", env=env, mounts=[prefix + "-backups:/backups:ro"], detach=False)
            print("PASS isolated backup/migration/restore regression; VPS/off-site deployment remains UNVERIFIED")
    except BaseException:
        for name in names:
            result = docker("logs", "--tail", "15", name, check=False)
            if result.stdout or result.stderr:
                print(name, result.stdout, result.stderr)
        raise
    finally:
        for name in reversed(names):
            docker("rm", "--force", "--volumes", name, check=False)
        for volume in volumes:
            docker("volume", "rm", volume, check=False)
        docker("network", "rm", prefix, check=False)


if __name__ == "__main__":
    main()
