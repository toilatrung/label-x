"""Create only the three application buckets; prove scoped access and public presigned HTTPS."""
import os
import secrets
import time
import urllib.error
import urllib.request

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

BUCKETS = ("labelx-snapshots", "labelx-evidence", "labelx-reports")


def client(endpoint, access, secret):
    return boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access,
        aws_secret_access_key=secret, region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
            connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}))


def main():
    endpoint = os.environ.get("S3_INTERNAL_ENDPOINT", "http://labelx-s3:9000")
    admin = client(endpoint, os.environ["ADMIN_ACCESS_KEY"], os.environ["ADMIN_SECRET_KEY"])
    for bucket in BUCKETS:
        try:
            admin.head_bucket(Bucket=bucket)
        except ClientError as error:
            if error.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
                raise
            admin.create_bucket(Bucket=bucket)
        admin.put_bucket_cors(Bucket=bucket, CORSConfiguration={"CORSRules": [{
            "AllowedOrigins": ["https://label-x.williamtrinh.online", "https://cvat.williamtrinh.online"],
            "AllowedMethods": ["GET", "HEAD", "PUT", "POST"], "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag", "Content-Length", "Content-Range"], "MaxAgeSeconds": 600}]})
    app = client(endpoint, os.environ["OBJECT_STORAGE_ACCESS_KEY"], os.environ["OBJECT_STORAGE_SECRET_KEY"])
    external = client(os.environ["OBJECT_STORAGE_ENDPOINT_URL"], os.environ["OBJECT_STORAGE_ACCESS_KEY"],
        os.environ["OBJECT_STORAGE_SECRET_KEY"])
    key, payload = "ops-init/" + secrets.token_hex(16), secrets.token_bytes(64)
    app.put_object(Bucket=BUCKETS[1], Key=key, Body=payload)
    try:
        url = external.generate_presigned_url("get_object", Params={"Bucket": BUCKETS[1], "Key": key}, ExpiresIn=600)
        # Certificate issuance is asynchronous on first installation. Never disable TLS validation.
        for attempt in range(60):
            try:
                request = urllib.request.Request(url, headers={"Origin": "https://label-x.williamtrinh.online"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    assert response.read() == payload
                    assert response.headers.get("Access-Control-Allow-Origin") == "https://label-x.williamtrinh.online"
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == 59:
                    raise RuntimeError("S3 public DNS/trusted HTTPS/presigned URL unavailable") from None
                time.sleep(5)
        print("PASS application buckets, scoped S3 write/read and public presigned HTTPS/CORS")
    finally:
        app.delete_object(Bucket=BUCKETS[1], Key=key)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"FAIL storage initialization: {type(error).__name__}", flush=True)
        raise SystemExit(1) from None
