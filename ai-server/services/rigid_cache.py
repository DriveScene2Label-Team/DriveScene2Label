"""Trusted, server-produced pre-filter VESPA state. Never deserialize upload files."""
import gzip
import hashlib
import json
import pickle

VERSION = "ds2l-rigid-v1"

def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def save(run_dir, scene, tracks, config, scope):
    path = run_dir / "rigid-state.pkl.gz"
    with gzip.open(path, "wb", compresslevel=1) as file:
        pickle.dump((scene, tracks, config), file, protocol=pickle.HIGHEST_PROTOCOL)
    manifest = {"version": VERSION, "scope": scope, "sha256": checksum(path)}
    (run_dir / "rigid-manifest.json").write_text(json.dumps(manifest))

def load(run_dir, scope):
    manifest = json.loads((run_dir / "rigid-manifest.json").read_text())
    path = run_dir / "rigid-state.pkl.gz"
    if manifest.get("version") != VERSION or manifest.get("scope") != scope or manifest.get("sha256") != checksum(path):
        raise ValueError("Rigid cache identity or checksum mismatch")
    with gzip.open(path, "rb") as file:
        return pickle.load(file)

def references(scene, tracks, selected):
    frames = {frame.sample_token: index for index, frame in enumerate(scene.frames)}
    refs = {}
    for track, token in selected.items():
        tid = int(track)
        if tid < 0 or tid >= len(tracks) or token not in frames or not any(t == frames[token] for t, _ in tracks[tid]):
            raise ValueError("Reference frame is not part of the source track")
        refs[tid] = frames[token]
    return refs
