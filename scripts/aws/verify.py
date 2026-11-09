"""Manual cloud validation: real browser edits in both environments, then recovery checks."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import urllib.request
import uuid
import zipfile

from environment import Environment, ROOT, log, run


def fetch(url, json_value=True):
    with urllib.request.urlopen(url, timeout=30) as response:
        body = response.read().decode()
    return json.loads(body) if json_value else body


def upload_dataset(url):
    """Use the backend's synthetic fixture to test storage, never model inference."""
    metadata = ROOT / "src/test/resources/nuscenes/v1.0-mini"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(metadata.glob("*.json")):
            archive.writestr("v1.0-mini/" + path.name, path.read_bytes())
        filenames = {row["filename"] for table in ("sample_data", "map")
                     for row in json.loads((metadata / f"{table}.json").read_text())}
        for filename in sorted(filenames):
            archive.writestr(filename, b"synthetic-media")
    data = buffer.getvalue()
    boundary = "ds2l-" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="storage-verification.zip"\r\n'
            'Content-Type: application/zip\r\n\r\n').encode() + data + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(url + "/api/dataset-uploads", data=body,
                                     headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(request, timeout=120) as response:
        uploaded = json.load(response)
    if uploaded["sceneCount"] != 1:
        raise RuntimeError("Uploaded dataset catalog does not match the verification fixture.")
    return {"id": uploaded["datasetId"], "sha256": hashlib.sha256(data).hexdigest()}


def verify(restore_only=False):
    environment = Environment()
    with environment.lock("verify"), environment.app_connections() as urls:
        if len(urls) != 2:
            raise RuntimeError("Both ECS and EKS applications must be running for validation.")
        images, _ = environment.read_control("images")
        environment.verify_application_image(images["app"])
        if restore_only:
            evidence, _ = environment.read_control("verification")
        else:
            evidence = {"records": [], "datasets": []}
            with tempfile.TemporaryDirectory(prefix="ds2l-verification-") as directory:
                for index, url in enumerate(urls):
                    record_path = Path(directory) / f"document-{index}.json"
                    settings = {**os.environ, "DS2L_BASE_URL": url, "DS2L_LIVE_ALLOW_LABEL_UPLOAD": "1", "DS2L_LABEL_RECORD": str(record_path)}
                    run(["npx", "playwright", "test", "-c", "playwright.live.config.ts", "labels.live.spec.ts"], cwd=ROOT / "frontend", env=settings)
                    evidence["records"].append(json.loads(record_path.read_text()))
                    evidence["datasets"].append(upload_dataset(url))
            environment.write_control("verification", evidence)
        for url in urls:
            for record in evidence["records"]:
                prefix = f"{url}/api/label-documents/{record['id']}"
                if fetch(prefix + "/original", False) != record["original"]:
                    raise RuntimeError("Original label bytes changed after restore/cross-environment read.")
                if fetch(prefix + "/download?revision=1") != record["saved"]:
                    raise RuntimeError("Saved label revision differs after restore/cross-environment read.")
                history = fetch(prefix + "/revisions")
                if not any(item["number"] == 1 for item in history):
                    raise RuntimeError("Saved revision history is missing.")
            if not evidence.get("datasets"):
                raise RuntimeError("Dataset evidence is missing; run verify without --restore-only first.")
            for dataset in evidence["datasets"]:
                with urllib.request.urlopen(f"{url}/api/dataset-uploads/{dataset['id']}/original", timeout=120) as response:
                    digest = hashlib.sha256(response.read()).hexdigest()
                if digest != dataset["sha256"]:
                    raise RuntimeError("Original dataset ZIP differs after restore/cross-environment read.")
        log("PASS: both environments preserve original ZIPs, labels, UI edits, revision history and downloads.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-only", action="store_true")
    verify(parser.parse_args().restore_only)
