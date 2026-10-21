"""Private staging and archive validation for Excel import work files.

This module owns temporary upload paths, archive safety checks, and cleanup.
Request/session state stays in the blueprint, while file permissions and
resource limits are centralized here for direct testing.
"""
from __future__ import annotations

import os
import re
import secrets
import stat
import time
import zipfile

from .private_work_files import (
    cleanup_stale_token_pairs,
    ensure_private_directory,
    is_private_work_token,
    save_private_upload,
)

# Uploads and review manifests contain personnel identifiers. Expire them
# automatically and keep them in owner-only directories/files.
_EXCEL_PENDING_TTL_SECONDS = 2 * 60 * 60
_EXCEL_PENDING_CLEANUP_INTERVAL_SECONDS = 10 * 60
_EXCEL_APPLY_CLAIM_TTL_SECONDS = 6 * 60 * 60
_APPLY_CLAIM_FILE_RE = re.compile(r"^([A-Za-z0-9_-]{32})\.apply\.lock$")



def _cleanup_stale_excel_apply_claims(directory: str, *, now: float | None = None) -> int:
    """Remove old claim files left by workers that terminated unexpectedly."""
    current = time.time() if now is None else float(now)
    cutoff = current - _EXCEL_APPLY_CLAIM_TTL_SECONDS
    removed = 0
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not _APPLY_CLAIM_FILE_RE.fullmatch(entry.name):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_mtime >= cutoff:
                    continue
                try:
                    os.unlink(entry.path)
                    removed += 1
                except OSError:
                    pass
    except OSError:
        return removed
    return removed


def _pending_excel_dir() -> str:
    directory = os.path.join(os.getenv("TMPDIR") or "/tmp", "employee_movements_excel_imports")
    directory = ensure_private_directory(directory)
    cleanup_stale_token_pairs(
        directory,
        _EXCEL_PENDING_TTL_SECONDS,
        interval_seconds=_EXCEL_PENDING_CLEANUP_INTERVAL_SECONDS,
    )
    _cleanup_stale_excel_apply_claims(directory)
    return directory


def _pending_excel_path(token: object) -> str | None:
    if not is_private_work_token(token):
        return None
    return os.path.join(_pending_excel_dir(), f"{token}.xlsx")


def _pending_excel_review_path(token: object) -> str | None:
    if not is_private_work_token(token):
        return None
    return os.path.join(_pending_excel_dir(), f"{token}.json")


def _validate_excel_archive(path: str | os.PathLike[str]) -> None:
    """Reject malformed or suspiciously expansive XLSX ZIP containers.

    The HTTP layer limits upload bytes; these limits additionally bound ZIP
    entries, decompressed size, compression ratios, and minimum XLSX structure.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 256:
                raise ValueError("Excel archive has an invalid number of entries")
            total_uncompressed = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted Excel archives are not supported")
                if info.file_size < 0 or info.compress_size < 0:
                    raise ValueError("Excel archive contains invalid size metadata")
                total_uncompressed += info.file_size
                if total_uncompressed > 64 * 1024 * 1024:
                    raise ValueError("Excel archive expands beyond the permitted limit")
                if info.file_size > 1024 * 1024 and info.compress_size == 0:
                    raise ValueError("Excel archive contains suspicious compression metadata")
                if info.compress_size and info.file_size / info.compress_size > 1000:
                    raise ValueError("Excel archive compression ratio is excessive")
            required = {"[Content_Types].xml", "xl/workbook.xml"}
            if not required.issubset({info.filename for info in infos}):
                raise ValueError("File is not a valid Excel workbook")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("File is not a valid Excel ZIP archive") from exc


def _remove_pending_excel(token: object) -> None:
    if not is_private_work_token(token):
        return
    for path in (_pending_excel_path(token), _pending_excel_review_path(token)):
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass



def _pending_excel_apply_claim_path(token: object) -> str | None:
    """Return the private exclusive-claim path for a valid staged import token."""
    if not is_private_work_token(token):
        return None
    return os.path.join(_pending_excel_dir(), f"{token}.apply.lock")


def _claim_pending_excel_apply(token: object) -> bool:
    """Atomically claim a staged import so concurrent POSTs cannot apply it twice.

    A stale claim left by a terminated worker may be replaced after a six-hour
    safety window. The private directory plus O_EXCL prevents two workers on
    the same upload filesystem from acquiring the token simultaneously.
    """
    path = _pending_excel_apply_claim_path(token)
    if not path:
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(2):
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError:
            try:
                info = os.stat(path, follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                return False
            if time.time() - info.st_mtime <= _EXCEL_APPLY_CLAIM_TTL_SECONDS:
                return False
            try:
                os.unlink(path)
            except OSError:
                return False
            continue
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                fd = -1
                stream.write(f"pid={os.getpid()} time={time.time():.6f}\n")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return True
    return False


def _release_pending_excel_apply(token: object) -> None:
    """Release this import's exclusive claim, if it is still present."""
    path = _pending_excel_apply_claim_path(token)
    if not path:
        return
    try:
        info = os.stat(path, follow_symlinks=False)
        if stat.S_ISREG(info.st_mode):
            os.unlink(path)
    except OSError:
        pass


def _save_pending_excel(upload) -> tuple[str, str]:
    token = secrets.token_urlsafe(24)
    path = _pending_excel_path(token)
    if not path:
        raise ValueError("Invalid generated Excel import token")
    save_private_upload(upload, path)
    try:
        _validate_excel_archive(path)
    except Exception:
        _remove_pending_excel(token)
        raise
    return token, path
