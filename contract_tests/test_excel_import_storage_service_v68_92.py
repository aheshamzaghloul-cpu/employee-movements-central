"""Filesystem and archive checks for the dependency-light Excel staging service."""
from __future__ import annotations

import importlib.util
import os
import stat
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "employee_movements"
SERVICES_ROOT = PACKAGE_ROOT / "services"
STORAGE_PATH = SERVICES_ROOT / "excel_import_storage.py"


def _load_storage():
    # Load this service under its real package name without importing the Flask
    # application factory (Flask is deliberately not needed for these tests).
    if "employee_movements" not in sys.modules:
        package = types.ModuleType("employee_movements")
        package.__path__ = [str(PACKAGE_ROOT)]
        sys.modules["employee_movements"] = package
    if "employee_movements.services" not in sys.modules:
        services_package = types.ModuleType("employee_movements.services")
        services_package.__path__ = [str(SERVICES_ROOT)]
        sys.modules["employee_movements.services"] = services_package
    module_name = "employee_movements.services.excel_import_storage_test"
    spec = importlib.util.spec_from_file_location(module_name, STORAGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # The relative import resolves against the genuine services package path.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _minimal_xlsx(path: Path, *, required=True):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        if required:
            archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")


class _Upload:
    def __init__(self, path: Path):
        self.path = path

    def save(self, stream):
        stream.write(self.path.read_bytes())


def test_archive_validation_accepts_minimal_valid_xlsx_container_and_rejects_missing_parts(tmp_path):
    storage = _load_storage()
    valid = tmp_path / "valid.xlsx"
    invalid = tmp_path / "missing-workbook.xlsx"
    _minimal_xlsx(valid)
    _minimal_xlsx(invalid, required=False)

    storage._validate_excel_archive(valid)
    try:
        storage._validate_excel_archive(invalid)
    except ValueError as exc:
        assert "valid Excel workbook" in str(exc)
    else:
        raise AssertionError("archive missing required XLSX parts should be rejected")


def test_archive_validation_rejects_corrupt_and_excessive_archives(tmp_path):
    storage = _load_storage()
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"not a zip archive")
    try:
        storage._validate_excel_archive(corrupt)
    except ValueError as exc:
        assert "valid Excel ZIP archive" in str(exc)
    else:
        raise AssertionError("corrupt archive should be rejected")

    excessive = tmp_path / "too-many-parts.xlsx"
    with zipfile.ZipFile(excessive, "w") as archive:
        for index in range(257):
            archive.writestr(f"part-{index}.xml", "x")
    try:
        storage._validate_excel_archive(excessive)
    except ValueError as exc:
        assert "invalid number of entries" in str(exc)
    else:
        raise AssertionError("archive with too many members should be rejected")


def test_pending_upload_stays_private_and_cleanup_removes_both_artifacts(tmp_path, monkeypatch):
    storage = _load_storage()
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    xlsx_source = tmp_path / "source.xlsx"
    _minimal_xlsx(xlsx_source)

    token, path = storage._save_pending_excel(_Upload(xlsx_source))
    assert storage._pending_excel_path(token) == path
    review_path = storage._pending_excel_review_path(token)
    assert review_path is not None
    private_files = sys.modules["employee_movements.services.private_work_files"]
    private_files.write_private_bytes(review_path, b'{"kind":"employees"}')
    assert stat.S_IMODE(Path(path).stat().st_mode) == 0o600
    assert stat.S_IMODE(Path(review_path).stat().st_mode) == 0o600
    parent = Path(path).parent
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700

    storage._remove_pending_excel(token)
    assert not Path(path).exists()
    assert not Path(review_path).exists()


def test_pending_paths_reject_invalid_tokens_without_touching_files(tmp_path, monkeypatch):
    storage = _load_storage()
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert storage._pending_excel_path("../escape") is None
    assert storage._pending_excel_review_path("not-a-token") is None
    storage._remove_pending_excel("../escape")
    assert list(tmp_path.iterdir()) == []


def test_blueprint_delegates_file_storage_and_workflow_rules_to_services():
    blueprint = (PACKAGE_ROOT / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "from ..services.excel_import_storage import (" in blueprint
    assert "from ..services.excel_import_workflow import (" in blueprint
    assert "def _validate_excel_archive(" not in blueprint
    assert "def _pending_excel_dir(" not in blueprint
    assert "def _selected_fields(action):" not in blueprint
    assert "def _is_selected_add(action):" not in blueprint
