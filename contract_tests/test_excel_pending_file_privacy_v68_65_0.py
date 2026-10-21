"""Filesystem-level regression tests for sensitive Excel import staging files."""
from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "employee_movements" / "services" / "private_work_files.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location("private_work_files_test_module", HELPER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Upload:
    def __init__(self, payload: bytes):
        self.payload = payload

    def save(self, destination):
        destination.write(self.payload)


def test_private_work_directory_and_files_are_owner_only(tmp_path):
    helper = _load_helper()
    root = helper.ensure_private_directory(tmp_path / "sensitive-imports")
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700

    token = "A" * 32
    upload_path = Path(root) / f"{token}.xlsx"
    helper.save_private_upload(_Upload(b"example-xlsx"), upload_path)
    assert upload_path.read_bytes() == b"example-xlsx"
    assert stat.S_IMODE(upload_path.stat().st_mode) == 0o600

    review_path = Path(root) / f"{token}.json"
    helper.write_private_bytes(review_path, b'{"kind":"employees"}')
    assert review_path.read_bytes() == b'{"kind":"employees"}'
    assert stat.S_IMODE(review_path.stat().st_mode) == 0o600


def test_private_directory_refuses_symlinks(tmp_path):
    helper = _load_helper()
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "linked-imports"
    try:
        link.symlink_to(real, target_is_directory=True)
    except (NotImplementedError, OSError):
        return
    try:
        helper.ensure_private_directory(link)
    except RuntimeError:
        pass
    else:
        raise AssertionError("A symlink must not be accepted as the private import directory")


def test_cleanup_removes_abandoned_pairs_but_preserves_recent_review_activity(tmp_path):
    helper = _load_helper()
    root = Path(helper.ensure_private_directory(tmp_path / "sensitive-imports"))
    now = 2_000_000_000.0
    ttl = 7_200

    stale_token = "S" * 32
    stale_paths = [root / f"{stale_token}.xlsx", root / f"{stale_token}.json"]
    for path in stale_paths:
        path.write_bytes(b"stale")
        os.chmod(path, 0o600)
        os.utime(path, (now - ttl - 100, now - ttl - 100))

    active_token = "A" * 32
    active_xlsx = root / f"{active_token}.xlsx"
    active_json = root / f"{active_token}.json"
    active_xlsx.write_bytes(b"uploaded")
    active_json.write_bytes(b"reviewed")
    for path in (active_xlsx, active_json):
        os.chmod(path, 0o600)
    os.utime(active_xlsx, (now - ttl - 50, now - ttl - 50))
    os.utime(active_json, (now - 100, now - 100))

    removed = helper.cleanup_stale_token_pairs(root, ttl, force=True, now=now)
    assert removed == 2
    assert not any(path.exists() for path in stale_paths)
    assert active_xlsx.exists() and active_json.exists()


def test_expiry_uses_the_newest_artifact_and_rejects_invalid_tokens(tmp_path):
    helper = _load_helper()
    assert helper.is_private_work_token("X" * 32)
    assert not helper.is_private_work_token("../outside")
    assert not helper.is_private_work_token("x" * 31)

    xlsx = tmp_path / "upload.xlsx"
    review = tmp_path / "review.json"
    xlsx.write_bytes(b"old")
    review.write_bytes(b"new")
    os.utime(xlsx, (1_000, 1_000))
    os.utime(review, (9_900, 9_900))
    assert not helper.pending_files_expired((xlsx, review), 3_600, now=10_000)
    assert helper.pending_files_expired((xlsx, review), 3_600, now=20_000)


def test_excel_import_uses_private_staging_and_expiration_contracts():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    storage = (ROOT / "employee_movements" / "services" / "excel_import_storage.py").read_text(encoding="utf-8")
    assert "_EXCEL_PENDING_TTL_SECONDS = 2 * 60 * 60" in storage
    assert "cleanup_stale_token_pairs(" in storage
    assert "ensure_private_directory(directory)" in storage
    assert "save_private_upload(upload, path)" in storage
    assert "write_private_bytes(review_path, review_payload)" in source
    assert "pending_files_expired((path, review_path), _EXCEL_PENDING_TTL_SECONDS)" in source
    assert "is_private_work_token(token)" in source


def test_private_upload_never_overwrites_an_existing_artifact(tmp_path):
    helper = _load_helper()
    root = helper.ensure_private_directory(tmp_path / "sensitive-imports")
    destination = Path(root) / ("A" * 32 + ".xlsx")
    destination.write_bytes(b"original")
    os.chmod(destination, 0o600)
    try:
        helper.save_private_upload(_Upload(b"replacement"), destination)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Private upload staging must use exclusive creation")
    assert destination.read_bytes() == b"original"


def test_failed_private_upload_removes_partial_file(tmp_path):
    helper = _load_helper()
    root = helper.ensure_private_directory(tmp_path / "sensitive-imports")
    destination = Path(root) / ("B" * 32 + ".xlsx")

    class FailingUpload:
        def save(self, stream):
            stream.write(b"partial-personnel-data")
            raise RuntimeError("synthetic upload failure")

    try:
        helper.save_private_upload(FailingUpload(), destination)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Synthetic write failure should propagate")
    assert not destination.exists()
