"""Check project data-protection rules using the official cfn-guard Python binding."""
import argparse
import json
from pathlib import Path

import guardpycfn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    rules = (Path(__file__).resolve().parents[2] / "infra/aws/security.guard").read_text()
    templates = sorted(args.directory.glob("*.json"))
    if not templates:
        raise RuntimeError("No CloudFormation templates found.")
    failed = False
    reports = {}
    for path in templates:
        report = guardpycfn.validate_with_guard(path.read_text(), rules, True)
        reports[path.name] = report
        if not report.get("success"):
            raise RuntimeError("cfn-guard could not evaluate " + path.name)
        checks = [item["container"]["RuleCheck"] for item in report["result"]["children"]]
        failed = failed or any(item["status"] == "FAIL" for item in checks)
        print(path.name, json.dumps(checks))
    (args.directory.parent / "security-report.json").write_text(json.dumps(reports, indent=2))
    if failed:
        raise SystemExit("Data-protection policy failed; inspect security-report.json.")


if __name__ == "__main__":
    main()
