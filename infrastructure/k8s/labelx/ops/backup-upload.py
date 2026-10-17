"""Encrypted DB backup plus content-addressed S3 object copies, without logging credentials."""
import hashlib
import json
import os
import secrets
import tempfile
import shutil
from io import BytesIO
import time
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

work = Path("/work")


def wait_for(name, failure="failed"):
    for _ in range(1800):
        if (work / failure).exists():
            raise RuntimeError("Backup companion failed")
        if (work / name).exists():
            return
        time.sleep(2)
    raise RuntimeError("Backup companion timed out")


def client(prefix):
    return boto3.client("s3", endpoint_url=os.environ[prefix + "ENDPOINT_URL"],
        aws_access_key_id=os.environ[prefix + "ACCESS_KEY"],
        aws_secret_access_key=os.environ[prefix + "SECRET_KEY"],
        region_name=os.environ.get(prefix + "REGION", "us-east-1"),
        config=Config(connect_timeout=10, read_timeout=120, retries={"max_attempts": 3}))


class LocalBackup:
    """Same-VPS copy only. Never represents offsite disaster recovery."""
    root = Path("/backups/local")

    def path(self, key):
        path = self.root / key
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Invalid backup path")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def upload_fileobj(self, stream, bucket, key, ExtraArgs=None):
        path = self.path(key)
        temporary = path.with_name(path.name + ".part-" + secrets.token_hex(8))
        try:
            with temporary.open("xb") as output:
                shutil.copyfileobj(stream, output)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def upload_file(self, source, bucket, key, ExtraArgs=None):
        with open(source, "rb") as stream:
            self.upload_fileobj(stream, bucket, key)

    def download_file(self, bucket, key, destination):
        shutil.copyfile(self.path(key), destination)

    def head_object(self, Bucket, Key):
        path = self.path(Key)
        if not path.exists():
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        with path.open("rb") as stream:
            return {"Metadata": {"sha256": hashlib.file_digest(stream, "sha256").hexdigest()}}

    def get_object(self, Bucket, Key):
        return {"Body": self.path(Key).open("rb")}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.upload_fileobj(BytesIO(Body), Bucket, Key)


def main():
    wait_for("dumped")
    backup_id = (work / "id").read_text()
    mode = os.environ.get("BACKUP_MODE", "offsite")
    if mode not in ("local", "offsite"):
        raise RuntimeError("Explicit backup mode local/offsite required")
    target = LocalBackup() if mode == "local" else client("BACKUP_S3_")
    bucket = "local-only" if mode == "local" else os.environ["BACKUP_S3_BUCKET"]
    prefix = os.environ.get("BACKUP_S3_PREFIX", "labelx").strip("/")
    encryption_key = bytes.fromhex(os.environ["BACKUP_ENCRYPTION_KEY"])
    source = client("OBJECT_STORAGE_")
    objects = []
    source_buckets = {os.environ["OBJECT_STORAGE_BUCKET_" + kind]
        for kind in ("SNAPSHOTS", "EVIDENCE", "REPORTS")}
    if os.environ.get("OBJECT_STORAGE_BUCKET"):
        source_buckets.add(os.environ["OBJECT_STORAGE_BUCKET"])
    for source_bucket in sorted(source_buckets):
        for page in source.get_paginator("list_objects_v2").paginate(Bucket=source_bucket):
            for entry in page.get("Contents", []):
                key = entry["Key"]
                with tempfile.TemporaryFile(dir=work) as stream:
                    source.download_fileobj(source_bucket, key, stream)
                    stream.seek(0)
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    destination = f"{prefix}/objects/{digest}"
                    try:
                        head = target.head_object(Bucket=bucket, Key=destination)
                        if head.get("Metadata", {}).get("sha256") != digest:
                            raise RuntimeError("Backup object checksum metadata mismatch")
                    except ClientError as error:
                        if error.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
                            raise
                        stream.seek(0)
                        target.upload_fileobj(stream, bucket, destination,
                            ExtraArgs={"Metadata": {"sha256": digest}})
                    # Metadata alone cannot prove remote object bytes survived upload/storage.
                    actual = hashlib.sha256()
                    actual_size = 0
                    with target.get_object(Bucket=bucket, Key=destination)["Body"] as remote:
                        while chunk := remote.read(8 * 1024 * 1024):
                            actual.update(chunk)
                            actual_size += len(chunk)
                    if actual.hexdigest() != digest:
                        raise RuntimeError("Remote S3 object checksum mismatch")
                    objects.append({"bucket": source_bucket, "key": key,
                        "backup_key": destination, "sha256": digest, "size": actual_size})
    nonce = secrets.token_bytes(12)
    encryptor = Cipher(algorithms.AES(encryption_key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(backup_id.encode())
    with (work / "database.dump").open("rb") as plain, (work / "database.dump.enc").open("wb") as encrypted:
        digest = hashlib.file_digest(plain, "sha256").hexdigest()
        plain.seek(0)
        encrypted.write(nonce)
        while chunk := plain.read(8 * 1024 * 1024):
            encrypted.write(encryptor.update(chunk))
        encrypted.write(encryptor.finalize())
        encrypted.write(encryptor.tag)
    dump_key = f"{prefix}/database/{backup_id}.dump.enc"
    with (work / "database.dump.enc").open("rb") as encrypted:
        encrypted_digest = hashlib.file_digest(encrypted, "sha256").hexdigest()
    target.upload_file(str(work / "database.dump.enc"), bucket, dump_key,
        ExtraArgs={"Metadata": {"sha256": encrypted_digest, "source-sha": os.environ["SOURCE_SHA"]}})
    target.download_file(bucket, dump_key, str(work / "downloaded.dump.enc"))
    with (work / "downloaded.dump.enc").open("rb") as downloaded, (work / "roundtrip.dump").open("wb") as restored:
        if hashlib.file_digest(downloaded, "sha256").hexdigest() != encrypted_digest:
            raise RuntimeError("Remote encrypted backup checksum mismatch")
        downloaded.seek(0)
        nonce = downloaded.read(12)
        downloaded.seek(-16, 2)
        tag = downloaded.read(16)
        remaining = downloaded.tell() - 28
        downloaded.seek(12)
        decryptor = Cipher(algorithms.AES(encryption_key), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(backup_id.encode())
        while remaining:
            chunk = downloaded.read(min(remaining, 8 * 1024 * 1024))
            if not chunk:
                raise RuntimeError("Remote backup truncated")
            restored.write(decryptor.update(chunk))
            remaining -= len(chunk)
        restored.write(decryptor.finalize())
    with (work / "roundtrip.dump").open("rb") as restored:
        if hashlib.file_digest(restored, "sha256").hexdigest() != digest:
            raise RuntimeError("Remote backup round-trip checksum mismatch")
    receipt = {"schema_version": 1, "backup_id": backup_id, "source_sha": os.environ["SOURCE_SHA"],
        "dump_key": dump_key, "dump_sha256": digest, "objects": objects,
        "mvp_acceptance": "unverified", "database_restore": "pending",
        "location": mode, "disaster_recovery": "unverified"}
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (work / "verified").touch()
    wait_for("restored")
    receipt["database_restore"] = "passed_disposable_database"
    content = json.dumps(receipt, indent=2).encode()
    (work / "receipt.json").write_bytes(content)
    # The completion receipt is written last. Incomplete uploads are never restore points.
    target.put_object(Bucket=bucket, Key=f"{prefix}/receipts/{backup_id}.json", Body=content,
        ContentType="application/json")
    Path(f"/backups/{backup_id}.json").write_bytes(content)
    print(f"PASS backup {backup_id}: {mode} copy, DB checksum, restored DB, {len(objects)} S3 objects; disaster recovery UNVERIFIED")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        (work / "upload-failed").touch()
        # SDK error strings may contain endpoint URLs. Keep logs credential-free.
        print(f"FAIL backup: {type(error).__name__}", flush=True)
        raise SystemExit(1) from None
