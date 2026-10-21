"""Keep current release provenance files synchronized and truthful."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _manifest(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_generic_and_versioned_release_manifests_are_identical():
    assert _manifest("REVIEW_MANIFEST.json") == _manifest("REVIEW_MANIFEST_v69.00.2.json") == _manifest("REVIEW_MANIFEST_v69.00.2_round32.json")


def test_release_manifest_version_matches_project_version_files():
    manifest = _manifest("REVIEW_MANIFEST.json")
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    project = __import__("tomllib").loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["version"] == version == project["project"]["version"]


def test_release_manifest_names_the_current_full_source_candidate_and_keeps_gate_closed():
    manifest = _manifest("REVIEW_MANIFEST.json")
    assert manifest["archive"] == "employee-movements-v69.00.2-full-source-upload-round32.zip"
    assert "NOT CLEARED FOR PRODUCTION" in manifest["validation"]["release_gate"]
    assert "NOT CLEARED FOR PRODUCTION" in manifest["artifact_status"]
