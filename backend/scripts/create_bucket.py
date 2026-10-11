"""Create the image bucket if it does not exist yet.

Used by the local docker compose stack (and safe to run against real S3 as a
one-off bootstrap). Retries while the object store is still starting, then
exits non-zero with the service's error if the credentials or policy are wrong.

    python scripts/create_bucket.py
"""

from __future__ import annotations

import os
import sys
import time

ATTEMPTS = 60
RETRY_SECONDS = 2


def main() -> int:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    bucket = os.environ.get("S3_BUCKET", "").strip()
    if not bucket:
        print("S3_BUCKET is not set", file=sys.stderr)
        return 2
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None
    client = boto3.client(
        "s3",
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID") or None,
        aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY") or None,
        config=Config(s3={"addressing_style": "path" if endpoint else "auto"}),
    )

    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            client.create_bucket(Bucket=bucket)
            print(f"created bucket {bucket}")
            return 0
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                print(f"bucket {bucket} already exists")
                return 0
            last_error = exc
        except BotoCoreError as exc:
            last_error = exc
        print(f"waiting for object storage ({attempt + 1}/{ATTEMPTS}): {last_error}")
        time.sleep(RETRY_SECONDS)

    print(f"could not create bucket {bucket}: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
