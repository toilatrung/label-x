#!/usr/bin/env python3
"""Wait for the CI S3 service and create its buckets through the application API."""

import os
import time


BUCKETS = ("labelx-snapshots", "labelx-evidence", "labelx-reports", "labelx-models")


def prepare(client, *, timeout=90, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    pending = list(BUCKETS)
    last_error = None
    while pending and clock() < deadline:
        bucket = pending[0]
        try:
            # Listing exercises the S3 gateway, filer and master before creation.
            existing = {item["Name"] for item in client.list_buckets()["Buckets"]}
            if bucket not in existing:
                client.create_bucket(Bucket=bucket)
            client.head_bucket(Bucket=bucket)
        except Exception as error:
            last_error = error
            print(f"Waiting for S3 bucket {bucket}: {type(error).__name__}", flush=True)
            sleep(min(2, max(0, deadline - clock())))
        else:
            pending.pop(0)
            print(f"S3 bucket ready: {bucket}", flush=True)
    if pending:
        raise RuntimeError(f"S3 readiness timed out; buckets unavailable: {', '.join(pending)}") from last_error


def main():
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["OBJECT_STORAGE_ENDPOINT_URL"],
        aws_access_key_id=os.environ["OBJECT_STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["OBJECT_STORAGE_SECRET_KEY"],
        region_name=os.environ.get("OBJECT_STORAGE_REGION", "us-east-1"),
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            retries={"total_max_attempts": 1},
            s3={"addressing_style": "path"},
        ),
    )
    prepare(client)


if __name__ == "__main__":
    main()
