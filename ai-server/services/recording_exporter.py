"""Rerun .rrd exporter run as a subprocess (rerun-sdk 0.38.1). Reads only the request JSON and lidar files."""
import argparse
import json
import math
import os
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np

APPLICATION_ID = "drivescene2label"
EXPORT_VERSION = "ds2l-rrd-v3"
ENTITIES = {"lidar": "world/lidar", "ego": "world/ego", "gt": "world/gt", "prediction": "world/prediction"}
# Text layers. Not part of the response entities: they hold no box instances, so viewer selection on them maps to nothing.
# Split by source (v3) so the app's GT / prediction toggles can hide the matching labels: "both" = a GT box and a
# prediction of the same class at the same place (hidden only when both sources are hidden).
LABELS_ENTITY = "world/labels"
LABEL_ENTITIES = {"gt": "world/labels/gt", "pred": "world/labels/pred", "both": "world/labels/both"}
GT_COLOR, PREDICTION_COLOR, EGO_COLOR = (0xFF, 0xCC, 0x4D), (0x4F, 0xE0, 0xD5), (0xC8, 0xCE, 0xD8)
BOTH_COLOR = (0xF2, 0xF4, 0xF6)  # label shared by a GT box and a prediction of the same class
# Label decluttering (Rerun has no screen-space label collision avoidance):
LABEL_RADIUS_M = 30.0   # only objects within this horizontal distance of the ego get a label (same rule as the camera tags)
MERGE_GT_PRED_M = 1.5   # a GT box and a prediction of the same class this close share one label
CLUSTER_M = 4.0         # same-class objects this close are labelled once as "class ×n"
LABEL_LIFT_M = 0.6      # labels float this far above the highest box top of their group
# GT display class = VESPA 8class comparison class of the nuScenes category, else the category itself
# (same table as frontend/src/lib/classes.ts and Spring LabelClasses; never coerced to "vehicle").
NUSC_8 = {"human.pedestrian.adult": "pedestrian", "human.pedestrian.child": "pedestrian", "human.pedestrian.construction_worker": "pedestrian",
          "human.pedestrian.police_officer": "pedestrian", "vehicle.bicycle": "bicycle", "vehicle.bus.bendy": "bus", "vehicle.bus.rigid": "bus",
          "vehicle.car": "car", "vehicle.construction": "construction_vehicle", "vehicle.motorcycle": "motorcycle", "vehicle.trailer": "trailer",
          "vehicle.truck": "truck",
          # ai-server/vespa-patches/0001 adds these two to 8class.
          "movable_object.barrier": "barrier", "movable_object.trafficcone": "traffic_cone"}
# Approximate nuScenes ego (Renault Zoe): origin at the rear axle on the ground, local x=L, y=W, z=H.
EGO_CENTER, EGO_HALF_SIZE = (1.3, 0.0, 0.78), (2.04, 0.87, 0.78)
EXIT_SDK_MISSING, EXIT_LIDAR_MISSING, EXIT_INVALID = 3, 4, 5


class ExportError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.exit_code = code


def finite(values, n, name):
    values = [float(v) for v in values]
    if len(values) != n or not all(math.isfinite(v) for v in values):
        raise ExportError(EXIT_INVALID, f"{name} must have {n} finite numbers")
    return values


def unit_wxyz(q, name):
    w, x, y, z = finite(q, 4, name)
    norm = math.sqrt(w*w + x*x + y*y + z*z)
    if abs(norm - 1) > 1e-3:
        raise ExportError(EXIT_INVALID, f"{name} must be a unit quaternion")
    return w/norm, x/norm, y/norm, z/norm


def rotation_matrix(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def lidar_world(path, lidar):
    if path.stat().st_size % 20:
        raise ExportError(EXIT_INVALID, "lidar file is not float32x5")
    raw = np.fromfile(path, dtype=np.float32)
    if raw.size % 5:
        raise ExportError(EXIT_INVALID, "lidar file is not float32x5")
    points = raw.reshape(-1, 5)[:, :3].astype(np.float64)
    points = points[np.isfinite(points).all(axis=1)]
    sensor = rotation_matrix(unit_wxyz(lidar["sensor_rotation"], "sensor_rotation"))
    ego = rotation_matrix(unit_wxyz(lidar["ego_rotation"], "ego_rotation"))
    points = points @ sensor.T + np.array(finite(lidar["sensor_translation"], 3, "sensor_translation"))  # sensor -> ego
    return points @ ego.T + np.array(finite(lidar["ego_translation"], 3, "ego_translation"))  # ego -> world


def height_colors(z, ground):
    # Navy (ground) -> light (3 m above ego origin); avoids the GT yellow and prediction mint.
    t = np.clip((z - ground + 1.0) / 4.0, 0, 1)[:, None]
    low, high = np.array([40, 60, 140]), np.array([235, 238, 248])
    return (low + (high - low) * t).astype(np.uint8)


def gt_class(category_name):
    if not category_name:
        return "GT"
    return NUSC_8.get(category_name, category_name)


def label_layer(gt, predictions, ego_xy):
    """Decluttered labels for one sample: [(position xyz, text, rgb, source)] with source gt | pred | both.
    Near objects only, GT+prediction of the same class at the same place share a label, same-class groups are merged
    ("pedestrian ×3"), and each label floats above its group. Without an ego position (no lidar) no labels are written."""
    if ego_xy is None:
        return []
    ex, ey = ego_xy
    items = []
    for source, rows in (("gt", gt), ("pred", predictions)):
        for i, box in enumerate(rows):
            x, y, z = finite(box["center"], 3, f"box {i} center")
            h = finite(box["size_wlh"], 3, f"box {i} size_wlh")[2]
            if math.hypot(x - ex, y - ey) > LABEL_RADIUS_M:
                continue
            cls = gt_class(box.get("category_name")) if source == "gt" else box["detection_name"]
            items.append({"cls": cls, "x": x, "y": y, "top": z + h / 2, "src": {source}})
    preds = [it for it in items if "pred" in it["src"]]
    merged = []
    for g in (it for it in items if "gt" in it["src"]):
        match = min((p for p in preds if p["cls"] == g["cls"] and math.hypot(p["x"] - g["x"], p["y"] - g["y"]) <= MERGE_GT_PRED_M),
                    key=lambda p: math.hypot(p["x"] - g["x"], p["y"] - g["y"]), default=None)
        if match is not None:
            preds.remove(match)
            g = {**g, "top": max(g["top"], match["top"]), "src": {"gt", "pred"}}
        merged.append(g)
    merged += preds
    merged.sort(key=lambda it: math.hypot(it["x"] - ex, it["y"] - ey))
    groups = []
    for it in merged:
        group = next((c for c in groups if c["cls"] == it["cls"] and math.hypot(c["x"] - it["x"], c["y"] - it["y"]) <= CLUSTER_M), None)
        if group is None:
            groups.append({**it, "n": 1, "src": set(it["src"])})
            continue
        n = group["n"] + 1
        group.update(x=group["x"] + (it["x"] - group["x"]) / n, y=group["y"] + (it["y"] - group["y"]) / n,
                     top=max(group["top"], it["top"]), n=n, src=group["src"] | it["src"])
    out = []
    for c in groups:
        source = "both" if c["src"] == {"gt", "pred"} else "gt" if c["src"] == {"gt"} else "pred"
        color = {"both": BOTH_COLOR, "gt": GT_COLOR, "pred": PREDICTION_COLOR}[source]
        out.append(([c["x"], c["y"], c["top"] + LABEL_LIFT_M], c["cls"] if c["n"] == 1 else f"{c['cls']} ×{c['n']}", color, source))
    return out


def labels_archetype(rr, rows):
    n = len(rows)
    return rr.Points3D(np.array([r[0] for r in rows], dtype=np.float32).reshape(n, 3), labels=[r[1] for r in rows],
                       colors=np.array([r[2] for r in rows], dtype=np.uint8).reshape(n, 3), radii=np.full(n, 0.12, dtype=np.float32), show_labels=True)


def boxes(rr, rows, color, labels):
    centers, half_sizes, quaternions = [], [], []
    for i, box in enumerate(rows):
        w, l, h = finite(box["size_wlh"], 3, f"box {i} size_wlh")
        if min(w, l, h) <= 0:
            raise ExportError(EXIT_INVALID, f"box {i} size_wlh must be positive")
        qw, qx, qy, qz = unit_wxyz(box["rotation_wxyz"], f"box {i} rotation_wxyz")
        centers.append(finite(box["center"], 3, f"box {i} center"))
        half_sizes.append([l/2, w/2, h/2])  # local x=L, y=W, z=H
        quaternions.append([qx, qy, qz, qw])  # API W,X,Y,Z -> Rerun x,y,z,w
    n = len(rows)
    # Every component is written even when empty so latest-at never shows the previous sample's boxes.
    return rr.Boxes3D(centers=np.array(centers, dtype=np.float32).reshape(n, 3),
                      half_sizes=np.array(half_sizes, dtype=np.float32).reshape(n, 3),
                      quaternions=np.array(quaternions, dtype=np.float32).reshape(n, 4),
                      colors=np.tile(np.array(color, dtype=np.uint8), (n, 1)), labels=labels,
                      show_labels=False)  # names are drawn by the decluttered LABELS_ENTITY; kept here for selection/hover


def export(request, data_root, output, rr):
    root = Path(data_root).resolve()
    with_predictions = request.get("job_id") is not None
    rec = rr.RecordingStream(APPLICATION_ID, recording_id=f"ds2l-recording-{request['recording_id']}")
    tmp = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
    counts = []
    try:
        rec.set_log_time_enabled(False)  # Only the "sample" and "timestamp" timelines.
        rec.save(tmp)
        rec.send_recording_name(request["scene_name"])
        rec.log("world", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
        rec.log(ENTITIES["ego"], rr.Boxes3D(centers=[EGO_CENTER], half_sizes=[EGO_HALF_SIZE], colors=[EGO_COLOR], labels=["ego"]), static=True)
        for position, sample in enumerate(request["samples"]):
            if sample["index"] != position:
                raise ExportError(EXIT_INVALID, "sample index must follow request order")
            rec.set_time("sample", sequence=sample["index"])
            rec.set_time("timestamp", timestamp=np.datetime64(int(sample["timestamp_us"]), "us"))
            lidar = sample.get("lidar")
            ego_xy = None
            if lidar is None:
                rec.log(ENTITIES["lidar"], rr.Points3D(np.zeros((0, 3), dtype=np.float32), colors=np.zeros((0, 3), dtype=np.uint8), radii=np.zeros(0, dtype=np.float32)))
                points = 0
            else:
                path = (root / lidar["relative_path"]).resolve()
                if not path.is_relative_to(root):
                    raise ExportError(EXIT_INVALID, "lidar path escapes the dataset root")
                if not path.is_file():
                    raise ExportError(EXIT_LIDAR_MISSING, "lidar file is missing")
                world = lidar_world(path, lidar)
                ego_t = finite(lidar["ego_translation"], 3, "ego_translation")
                ego_q = unit_wxyz(lidar["ego_rotation"], "ego_rotation")
                rec.log(ENTITIES["lidar"], rr.Points3D(world.astype(np.float32), colors=height_colors(world[:, 2], ego_t[2]), radii=0.04))
                rec.log(ENTITIES["ego"], rr.Transform3D(translation=ego_t, quaternion=[*ego_q[1:], ego_q[0]]))
                points = len(world)
                ego_xy = (ego_t[0], ego_t[1])
            gt = sample.get("gt") or []
            rec.log(ENTITIES["gt"], boxes(rr, gt, GT_COLOR, [b.get("category_name") or "GT" for b in gt]))
            predictions = sample.get("predictions") or []
            if predictions and not with_predictions:
                raise ExportError(EXIT_INVALID, "predictions require job_id")
            if with_predictions:
                rec.log(ENTITIES["prediction"], boxes(rr, predictions, PREDICTION_COLOR, [b["detection_name"] for b in predictions]))
            # Written every sample (also empty) so latest-at never keeps the previous sample's labels.
            layer = label_layer(gt, predictions if with_predictions else [], ego_xy)
            for source, entity in LABEL_ENTITIES.items():
                rec.log(entity, labels_archetype(rr, [r for r in layer if r[3] == source]))
            counts.append({"index": sample["index"], "sample_token": sample["sample_token"], "lidar_points": points,
                           "gt_boxes": len(gt), "prediction_boxes": len(predictions)})
        rec.flush()
        rec.disconnect()
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    return {"sdk_version": rr.__version__, "export_version": EXPORT_VERSION, "application_id": APPLICATION_ID,
            "rerun_recording_id": f"ds2l-recording-{request['recording_id']}", "samples": counts}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--request", required=True)
    p.add_argument("--data-root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--summary", help="Write per-sample counts as JSON here (stdout when omitted).")
    a = p.parse_args()
    try:
        import rerun as rr
    except ImportError:
        print("rerun-sdk is not installed in this Python environment", file=sys.stderr)
        return EXIT_SDK_MISSING
    try:
        summary = export(json.loads(Path(a.request).read_text()), a.data_root, Path(a.output).absolute(), rr)
    except ExportError as exc:
        print(f"export failed: {exc}", file=sys.stderr)
        return exc.exit_code
    text = json.dumps(summary, separators=(",", ":"))
    if a.summary:
        Path(a.summary).write_text(text)
    for row in summary["samples"]:
        print("sample={index} lidar_points={lidar_points} gt_boxes={gt_boxes} prediction_boxes={prediction_boxes}".format(**row))
    if not a.summary:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
