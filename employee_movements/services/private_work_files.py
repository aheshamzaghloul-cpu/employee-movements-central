"""Private, bounded-lifetime file handling for sensitive import work files.

This module deliberately uses only the Python standard library so its filesystem
safety behavior can be tested without bootstrapping the Flask application.
"""
from __future__ import annotations

import os
import re
import stat
import threading
import time

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32}$")
_TOKEN_FILE_RE = re.compile(r"^([A-Za-z0-9_-]{32})\.(xlsx|json)$")
_CLEANUP_LOCK = threading.Lock()
_LAST_CLEANUP: dict[str, float] = {}


def is_private_work_token(token: object) -> bool:
    return isinstance(token, str) and _TOKEN_RE.fullmatch(token) is not None


def ensure_private_directory(path: str | os.PathLike[str]) -> str:
    """Create or validate an app-owned directory inaccessible to other users."""
    directory = os.path.abspath(os.fspath(path))
    try:
        os.mkdir(directory, 0o700)
    except FileExistsError:
        pass

    info = os.lstat(directory)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise RuntimeError("Private work path is not a real directory")
    if info.st_uid != os.geteuid():
        raise PermissionError("Private work directory must be owned by the application user")

    # Also tighten a directory created by an older version with permissive mode.
    if stat.S_IMODE(info.st_mode) != 0o700:
        os.chmod(directory, 0o700)
    verified = os.lstat(directory)
    if not stat.S_ISDIR(verified.st_mode) or verified.st_uid != os.geteuid() or stat.S_IMODE(verified.st_mode) != 0o700:
        raise PermissionError("Unable to enforce private work directory permissions")
    return directory


def save_private_upload(upload, destination: str | os.PathLike[str]) -> None:
    """Save a Werkzeug-style upload to a new file with mode 0600, never overwrite."""
    path = os.path.abspath(os.fspath(destination))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            upload.save(stream)
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def write_private_bytes(destination: str | os.PathLike[str], data: bytes) -> None:
    """Write sensitive review metadata with explicit owner-only permissions."""
    path = os.path.abspath(os.fspath(destination))
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if fd >= 0:
            os.close(fd)
        raise


def pending_files_expired(paths, ttl_seconds: int, *, now: float | None = None) -> bool:
    """Return true when none of the existing regular files has recent activity."""
    current = time.time() if now is None else float(now)
    mtimes = []
    for path in paths:
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            mtimes.append(info.st_mtime)
    return not mtimes or current - max(mtimes) > max(1, int(ttl_seconds))


def touch_private_files(paths) -> None:
    """Refresh activity for existing regular work files without following symlinks."""
    for path in paths:
        try:
            info = os.stat(path, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode):
                os.utime(path, None, follow_symlinks=False)
        except OSError:
            continue


def cleanup_stale_token_pairs(
    directory: str | os.PathLike[str],
    ttl_seconds: int,
    *,
    interval_seconds: int = 600,
    force: bool = False,
    now: float | None = None,
) -> int:
    """Delete old XLSX/JSON artifacts as pairs, at most once per interval per process."""
    root = ensure_private_directory(directory)
    current_wall = time.time() if now is None else float(now)
    current_mono = time.monotonic()
    with _CLEANUP_LOCK:
        last = _LAST_CLEANUP.get(root, 0.0)
        if not force and current_mono - last < max(1, int(interval_seconds)):
            return 0
        _LAST_CLEANUP[root] = current_mono

    groups: dict[str, list[tuple[str, float]]] = {}
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                match = _TOKEN_FILE_RE.fullmatch(entry.name)
                if not match:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    continue
                groups.setdefault(match.group(1), []).append((entry.path, info.st_mtime))
    except OSError:
        return 0

    cutoff = current_wall - max(1, int(ttl_seconds))
    removed = 0
    for files in groups.values():
        # The review JSON is created later than the uploaded XLSX; use the newest
        # timestamp so a recently reviewed active pair is not partially removed.
        if max(mtime for _, mtime in files) >= cutoff:
            continue
        for path, _ in files:
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass
    return removed
