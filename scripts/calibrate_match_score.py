#!/usr/bin/env python3
"""Measure the search.match-score.* anchors from the running Spring search API (stdlib only).

For each aggregation:
  upper (100 points) = median score short queries get on the scenes they describe (--queries, e.g. "night" on the
                       night scenes). Users search with short phrases, which score lower than a full sentence;
                       an anchor from long descriptions put correct short-query hits at about 70 points.
  lower (0 points)   = 90th percentile of the scores unrelated text gets against every scene.
Also prints, for reference, the scores of each scene's own nuScenes description and how many correct / wrong
short-query pairs reach 80 points with the new anchors (the scale changes the numbers, not the ranking).
Re-run after changing the CLIP model/preprocess or the dataset (e.g. trainval, with its own query file),
then update application.properties and docs/search-match-score.md.

  python3 scripts/calibrate_match_score.py [--api http://127.0.0.1:8080] [--dataset-id N] [--queries FILE]
"""
import argparse
import json
import pathlib
import statistics
import sys
import urllib.parse
import urllib.request

UNRELATED = [  # nothing a driving camera sees; also one string of random letters
    "asdkjh qwe", "a giraffe on the beach", "purple elephant", "a plate of spaghetti",
    "snowy mountain ski slope", "underwater coral reef", "a cat sleeping on a sofa", "fireworks over a castle",
]
AGGREGATIONS = {"TOP_K_AVERAGE": "top-k-average", "MAX": "max", "AVERAGE": "average"}


def search(api: str, q: str, aggregation: str, dataset_id):
    params = {"q": q, "k": 100, "aggregation": aggregation}
    if dataset_id is not None:
        params["datasetId"] = dataset_id
    with urllib.request.urlopen(f"{api}/api/search/scenes?{urllib.parse.urlencode(params)}", timeout=120) as r:
        return json.load(r)


def percentile(values, p):
    v = sorted(values)
    return v[round(p * (len(v) - 1))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8080")
    ap.add_argument("--dataset-id", type=int)
    ap.add_argument("--queries", default=str(pathlib.Path(__file__).with_name("match_score_queries.mini.json")))
    a = ap.parse_args()
    queries = json.loads(pathlib.Path(a.queries).read_text())["queries"]

    first = search(a.api, "road", "TOP_K_AVERAGE", a.dataset_id)
    scenes = {(s["datasetId"], s["sceneId"]): s for s in first["scenes"]}
    described = {key: s["description"] for key, s in scenes.items() if (s.get("description") or "").strip()}
    names = {s["sceneName"] for s in scenes.values()}
    missing = sorted({n for q in queries for n in q["scenes"]} - names)
    if missing:
        print(f"query file names scenes that are not in the search results: {missing}", file=sys.stderr)
        return 1
    if len(described) < 3:
        print(f"need at least 3 scenes with a description and image embeddings, found {len(described)}", file=sys.stderr)
        return 1
    print(f"# model={first['modelName']} preprocess={first['preprocess']} scenes={len(scenes)} "
          f"described={len(described)} imageTopK={first['imageTopK']}")
    lines = [f"search.match-score.model-name={first['modelName']}", f"search.match-score.preprocess={first['preprocess']}"]
    for agg, key in AGGREGATIONS.items():
        own, others, unrelated, rank1 = [], [], [], 0
        for scene_key, text in described.items():
            result = search(a.api, text, agg, a.dataset_id)["scenes"]
            for s in result:
                (own if (s["datasetId"], s["sceneId"]) == scene_key else others).append(s["score"])
            rank1 += bool(result) and (result[0]["datasetId"], result[0]["sceneId"]) == scene_key
        for text in UNRELATED:
            unrelated += [s["score"] for s in search(a.api, text, agg, a.dataset_id)["scenes"]]
        right, wrong, short_rank1 = [], [], 0
        for q in queries:
            result = search(a.api, q["query"], agg, a.dataset_id)["scenes"]
            for s in result:
                (right if s["sceneName"] in q["scenes"] else wrong).append(s["score"])
            short_rank1 += bool(result) and result[0]["sceneName"] in q["scenes"]
        lower, upper = percentile(unrelated, 0.9), statistics.median(right)
        points = lambda v: max(0, min(100, round(100 * (v - lower) / (upper - lower)))) if upper > lower else 0
        share80 = lambda values: f"{100 * sum(points(v) >= 80 for v in values) / len(values):.0f}%"
        print(f"# {agg}: short queries n={len(queries)} right pairs={len(right)} median={upper:.3f} "
              f"(ranked first {short_rank1}/{len(queries)}) | wrong pairs={len(wrong)} median={statistics.median(wrong):.3f} | "
              f">=80 points: right {share80(right)}, wrong {share80(wrong)}")
        print(f"# {agg}: own description n={len(own)} median={statistics.median(own):.3f} min={min(own):.3f} max={max(own):.3f} "
              f"(ranked first {rank1}/{len(described)}) | other scenes median={statistics.median(others):.3f} | "
              f"unrelated n={len(unrelated)} median={statistics.median(unrelated):.3f} p90={lower:.3f} max={max(unrelated):.3f}")
        if upper <= lower:
            print(f"# {agg}: upper <= lower, calibration unusable for this data", file=sys.stderr)
            return 1
        lines += [f"search.match-score.{key}.lower={lower:.3f}", f"search.match-score.{key}.upper={upper:.3f}"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
