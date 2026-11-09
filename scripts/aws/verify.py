"""Manual cloud validation: real browser edits in both environments, then recovery checks."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import urllib.request

from environment import Environment, ROOT, log, run


def fetch(url, json_value=True):
    with urllib.request.urlopen(url, timeout=30) as response:
        body = response.read().decode()
    return json.loads(body) if json_value else body


def verify(restore_only=False):
    environment = Environment()
    with environment.lock("verify"), environment.app_connections() as urls:
        if len(urls) != 2:
            raise RuntimeError("Both ECS and EKS applications must be running for validation.")
        if restore_only:
            evidence, _ = environment.read_control("verification")
        else:
            evidence = {"records": []}
            with tempfile.TemporaryDirectory(prefix="ds2l-verification-") as directory:
                for index, url in enumerate(urls):
                    record_path = Path(directory) / f"document-{index}.json"
                    settings = {**os.environ, "DS2L_BASE_URL": url, "DS2L_LIVE_ALLOW_LABEL_UPLOAD": "1", "DS2L_LABEL_RECORD": str(record_path)}
                    run(["npx", "playwright", "test", "-c", "playwright.live.config.ts", "labels.live.spec.ts"], cwd=ROOT / "frontend", env=settings)
                    evidence["records"].append(json.loads(record_path.read_text()))
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
        log("PASS: both environments preserve original labels, UI edits, revision history and downloaded JSON.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-only", action="store_true")
    verify(parser.parse_args().restore_only)
