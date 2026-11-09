"""Fetch immutable upload archives into an atomically published, bounded local cache."""
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from threading import Lock

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config


class UploadedDatasetCache:
    def __init__(self):
        self.root = Path(os.environ.get("UPLOAD_ROOT", "/uploads")).resolve()
        self.bucket = os.environ.get("UPLOAD_S3_BUCKET", "").strip()
        self.max_expanded = int(os.environ.get("UPLOAD_MAX_EXPANDED_BYTES", str(4 * 1024 ** 3)))
        self.lock = Lock()
        self.client = None

    def ensure(self, key):
        if not re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", key):
            raise ValueError("Invalid dataset key")
        parent = self.root / "datasets"
        target = (parent / key).resolve()
        if not target.is_relative_to(parent):
            raise ValueError("Invalid dataset path")
        if target.is_dir():
            return target
        if not self.bucket:
            return target  # Local Compose shares the upload volume; configured() reports missing files.
        with self.lock:
            if target.is_dir():
                return target
            if self.client is None:
                self.client = boto3.client("s3", config=Config(connect_timeout=5, read_timeout=60,
                                            retries={"total_max_attempts": 3, "mode": "standard"}))
            object_key = f"uploads/{key}.zip"
            if self.client.head_object(Bucket=self.bucket, Key=object_key)["ContentLength"] > 512 * 1024 ** 2:
                raise ValueError("Upload archive exceeds 512MB")
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".fetch-", dir=parent) as temporary:
                archive = Path(temporary) / "archive.zip"
                self.client.download_file(self.bucket, object_key, str(archive), Config=TransferConfig(use_threads=False))
                if archive.stat().st_size > 512 * 1024 ** 2:
                    raise ValueError("Upload archive exceeds 512MB")
                extracted = Path(temporary) / "data"
                extracted.mkdir()
                extract_archive(archive, extracted, self.max_expanded)
                extracted.rename(target)
        return target


def extract_archive(archive, root, max_expanded):
    expanded = 0
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if not entries or len(entries) > 100000:
            raise ValueError("Invalid archive entry count")
        for entry in entries:
            name = entry.filename
            if (not name or name.startswith("/") or "\\" in name or ":" in name or ".." in name.split("/")
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError("Invalid archive path")
            target = (root / name).resolve()
            if target == root or not target.is_relative_to(root):
                raise ValueError("Archive path outside dataset")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            expanded += entry.file_size
            if expanded > max_expanded:
                raise ValueError("Expanded archive exceeds limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as input_file, target.open("xb") as output:
                shutil.copyfileobj(input_file, output, length=65536)
