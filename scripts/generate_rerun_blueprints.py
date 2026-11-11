"""Generate the Rerun blueprints the web app sends to the viewer to mirror its GT / 예측 / 클래스 이름 toggles.

The Rerun Web Viewer 0.38.1 JS API cannot hide entities, but it applies a blueprint received through a log channel.
A blueprint only depends on the application id and entity paths (not on recording data), so the eight toggle
combinations are generated once and served as static files.

Run with the exporter's SDK (rerun-sdk 0.38.1), and regenerate whenever the SDK version, the application id or the
entity paths in ai-server/services/recording_exporter.py change:
    PYTHONPATH=<venv>/site-packages/rerun_sdk <venv>/bin/python scripts/generate_rerun_blueprints.py
"""
import sys
import uuid
from pathlib import Path

import rerun as rr
import rerun.blueprint as rrb

EXPECTED_SDK = "0.38.1"
APPLICATION_ID = "drivescene2label"
OUT = Path(__file__).resolve().parents[1] / "frontend/public/rerun-blueprints"
# Same view/container ids in every variant. Note: Rerun 0.38.1 still resets the 3D camera when another blueprint store
# becomes active, so toggling a layer re-frames the view (the app restores timeline, frame and pause state).
VIEW_ID = uuid.UUID("6c6a3c39-3d6b-4d2b-9a77-1f3a2b8c0d11")
ROOT_ID = uuid.UUID("6c6a3c39-3d6b-4d2b-9a77-1f3a2b8c0d12")


def contents(gt: bool, pred: bool, names: bool) -> list[str]:
    rules = ["+ /**"]
    if not gt:
        rules += ["- /world/gt/**", "- /world/labels/gt/**"]
    if not pred:
        rules += ["- /world/prediction/**", "- /world/labels/pred/**"]
    if not gt and not pred:
        rules.append("- /world/labels/both/**")
    if not names:
        rules.append("- /world/labels/**")
    return rules


def write_blueprint(path: Path, gt: bool, pred: bool, names: bool) -> None:
    view = rrb.Spatial3DView(origin="/", contents=contents(gt, pred, names), name="3D")
    view.id = VIEW_ID
    bp = rrb.Blueprint(view, auto_layout=False, auto_views=False)
    bp.root_container.id = ROOT_ID
    # Official .rbl writer: one blueprint store, applied by the viewer when received (no recording store).
    bp.save(APPLICATION_ID, str(path))


def check(path: Path) -> None:
    from rerun.chunk import RrdReader
    reader = RrdReader(path)
    if list(reader.recordings()) or len(list(reader.blueprints())) != 1:
        raise SystemExit(f"{path.name}: expected exactly one blueprint store and no recording store")


def main() -> int:
    if rr.__version__ != EXPECTED_SDK:
        print(f"rerun-sdk {EXPECTED_SDK} required, found {rr.__version__}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for gt in (True, False):
        for pred in (True, False):
            for names in (True, False):
                name = f"gt{int(gt)}-pred{int(pred)}-names{int(names)}.rbl"
                write_blueprint(OUT / name, gt, pred, names)
                check(OUT / name)
                print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
