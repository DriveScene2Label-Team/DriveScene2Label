"""Fetch immutable upload archives into an atomically published, bounded local cache."""
import os
import re
import shutil
import stat
import tempfile
import zipfile
import gzip
import tarfile
from pathlib import Path
from threading import Lock

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

MAX_ARCHIVE_BYTES = 5_000_000_000

class UploadedDatasetCache:
    def __init__(self):
        self.root = Path(os.environ.get("UPLOAD_ROOT", "/uploads")).resolve()
        self.bucket = os.environ.get("UPLOAD_S3_BUCKET", "").strip()
        self.max_expanded = int(os.environ.get("UPLOAD_MAX_EXPANDED_BYTES", str(8 * 1024 ** 3)))
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
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            except self.client.exceptions.NoSuchKey:
                object_key = f"uploads/{key}.tar.gz"
                response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            response["Body"].close()
            if response["ContentLength"] > MAX_ARCHIVE_BYTES:
                raise ValueError("Upload archive exceeds 5GB")
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".fetch-", dir=parent) as temporary:
                archive = Path(temporary) / "archive"
                self.client.download_file(self.bucket, object_key, str(archive), Config=TransferConfig(use_threads=False))
                if archive.stat().st_size > MAX_ARCHIVE_BYTES:
                    raise ValueError("Upload archive exceeds 5GB")
                extracted = Path(temporary) / "data"
                extracted.mkdir()
                extract_archive(archive, extracted, self.max_expanded)
                extracted.rename(target)
        return target


def extract_archive(archive, root, max_expanded):
    with Path(archive).open('rb') as stream:
        if stream.read(2) == b'\x1f\x8b':
            return extract_tar_gzip(archive, root, max_expanded)
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
            if (target == root and not entry.is_dir()) or not target.is_relative_to(root):
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


def extract_tar_gzip(archive, root, max_expanded):
    root = Path(root).resolve()
    expanded = 0
    count = 0
    with gzip.open(archive, 'rb') as compressed:
        with tarfile.open(fileobj=compressed, mode='r|') as source:
            for entry in source:
                count += 1
                name = entry.name
                if (count > 100000 or not name or name.startswith('/') or '\\' in name or ':' in name
                        or '..' in name.split('/') or entry.issparse() or not (entry.isfile() or entry.isdir())):
                    raise ValueError('Invalid TAR entry: only regular files and directories are allowed')
                target = (root / name).resolve()
                if not target.is_relative_to(root) or (target == root and not entry.isdir()):
                    raise ValueError('Archive path outside dataset')
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                expanded += entry.size
                if expanded > max_expanded:
                    raise ValueError('Expanded archive exceeds limit')
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(entry) as input_file, target.open('xb') as output:
                    shutil.copyfileobj(input_file, output, length=65536)
            if count == 0:
                raise ValueError('Empty TAR archive')
        # Check the gzip trailer even if the TAR end marker was reached first.
        padding = 0
        while chunk := compressed.read(65536):
            padding += len(chunk)
            if padding > 16 * 1024 ** 2:
                raise ValueError('Excessive TAR trailing data')
