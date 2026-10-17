"""Private versioned objects. S3 with required versioning in production; filesystem for development."""

import hashlib
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import boto3

from app.core.config import settings


class ObjectStore:
    def __init__(self):
        self.config = settings()
        self.root = Path(self.config.source_storage_path).resolve()

    def put(self, tenant: str, stream: BinaryIO) -> dict:
        key = f"{uuid.UUID(tenant)}/{uuid.uuid4()}"
        digest = hashlib.sha256()
        size = 0
        with tempfile.TemporaryFile() as staged:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > self.config.max_upload_bytes:
                    raise ValueError("Source exceeds upload limit")
                digest.update(chunk)
                staged.write(chunk)
            staged.seek(0)
            if self.config.source_s3_bucket:
                client = boto3.client("s3", region_name=self.config.source_s3_region)
                if (
                    client.get_bucket_versioning(Bucket=self.config.source_s3_bucket).get("Status")
                    != "Enabled"
                ):
                    raise ValueError("S3 bucket versioning is required")
                privacy = client.get_public_access_block(Bucket=self.config.source_s3_bucket).get(
                    "PublicAccessBlockConfiguration", {}
                )
                if not all(
                    privacy.get(key) is True
                    for key in [
                        "BlockPublicAcls",
                        "IgnorePublicAcls",
                        "BlockPublicPolicy",
                        "RestrictPublicBuckets",
                    ]
                ):
                    raise ValueError("S3 public access must be blocked")
                if not self.config.source_kms_key:
                    raise ValueError("An explicit source-object KMS key is required")
                response = client.put_object(
                    Bucket=self.config.source_s3_bucket,
                    Key=key,
                    Body=staged,
                    ServerSideEncryption="aws:kms",
                    SSEKMSKeyId=self.config.source_kms_key,
                )
                version = response["VersionId"]
            else:
                if self.config.environment == "production":
                    raise ValueError("Production requires versioned private S3 storage")
                path = self.root / key
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as output:
                    while chunk := staged.read(1024 * 1024):
                        output.write(chunk)
                version = key.split("/")[1]
        return {
            "object_key": key,
            "object_version": version,
            "sha256": digest.hexdigest(),
            "size": size,
        }

    @contextmanager
    def local(self, key: str, version: str) -> Iterator[Path]:
        # Keys are opaque server-generated UUID pairs, never supplied filesystem paths.
        parts = key.split("/")
        if len(parts) != 2 or any(str(uuid.UUID(part)) != part for part in parts):
            raise ValueError("Invalid object key")
        if not self.config.source_s3_bucket:
            yield self.root / key
        else:
            client = boto3.client("s3", region_name=self.config.source_s3_region)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "source"
                client.download_file(
                    self.config.source_s3_bucket, key, str(path), ExtraArgs={"VersionId": version}
                )
                yield path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
