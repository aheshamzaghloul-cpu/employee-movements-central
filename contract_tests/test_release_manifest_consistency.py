"""Keep current release provenance files synchronized and truthful."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _manifest(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_generic_and_versioned_release_manifests_are_identical():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    candidates = sorted(ROOT.glob(f"REVIEW_MANIFEST_v{version}_round*.json"))
    assert len(candidates) == 1, f"expected one versioned manifest, got {[p.name for p in candidates]}"
    assert _manifest("REVIEW_MANIFEST.json") == json.loads(candidates[0].read_text(encoding="utf-8"))


def test_release_manifest_version_matches_project_version_files():
    manifest = _manifest("REVIEW_MANIFEST.json")
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    project = __import__("tomllib").loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["version"] == version == project["project"]["version"]
    assert isinstance(manifest["review_round"], int) and manifest["review_round"] >= 1
    candidates = sorted(ROOT.glob(f"REVIEW_MANIFEST_v{version}_round*.json"))
    assert len(candidates) == 1
    assert candidates[0].stem.endswith(f"_round{manifest['review_round']}")


def test_release_manifest_names_the_current_full_source_candidate_and_keeps_gate_closed():
    manifest = _manifest("REVIEW_MANIFEST.json")
    assert isinstance(manifest["review_round"], int) and manifest["review_round"] >= 1
    assert manifest["archive"] == f"employee-movements-v{manifest['version']}-full-source-upload-round{manifest['review_round']}.zip"
    assert "NOT CLEARED FOR PRODUCTION" in manifest["validation"]["release_gate"]
    assert "NOT CLEARED FOR PRODUCTION" in manifest["artifact_status"]
