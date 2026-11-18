"""Bounded local screenshot storage for browser checks (BROW-1).

Files live under a configured root as `{check_id}.png`. The database stores
only that relative name — never an absolute path from the client.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_SAFE_NAME = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.png$",
    re.IGNORECASE,
)


def screenshot_filename(check_id: UUID) -> str:
    return f"{check_id}.png"


def clamp_png_bytes(data: bytes | None, *, max_bytes: int) -> bytes | None:
    """Accept a PNG only when magic + size look sane."""
    if data is None:
        return None
    if not isinstance(data, (bytes, bytearray)):
        return None
    raw = bytes(data)
    if len(raw) < len(_PNG_MAGIC) or len(raw) > max_bytes:
        return None
    if not raw.startswith(_PNG_MAGIC):
        return None
    return raw


def write_screenshot(
    root: Path,
    check_id: UUID,
    png: bytes,
    *,
    max_bytes: int,
) -> str | None:
    """Write PNG to disk. Returns relative filename or None on skip/failure."""
    payload = clamp_png_bytes(png, max_bytes=max_bytes)
    if payload is None:
        return None
    try:
        root.mkdir(parents=True, exist_ok=True)
        name = screenshot_filename(check_id)
        target = root / name
        # Refuse path escape even if root is weirdly linked.
        if target.resolve().parent != root.resolve():
            logger.warning("Screenshot path escaped storage root")
            return None
        tmp = target.with_suffix(".png.tmp")
        tmp.write_bytes(payload)
        tmp.replace(target)
        return name
    except OSError as exc:
        logger.warning("Screenshot write failed (%s)", exc.__class__.__name__)
        return None


def read_screenshot(
    root: Path,
    relative_path: str | None,
    *,
    max_bytes: int,
) -> bytes | None:
    """Read a stored screenshot after validating the relative name."""
    if not relative_path or not _SAFE_NAME.match(relative_path):
        return None
    target = (root / relative_path).resolve()
    try:
        if target.parent != root.resolve():
            return None
        if not target.is_file():
            return None
        data = target.read_bytes()
    except OSError as exc:
        logger.warning("Screenshot read failed (%s)", exc.__class__.__name__)
        return None
    return clamp_png_bytes(data, max_bytes=max_bytes)


def delete_screenshot(root: Path, relative_path: str | None) -> None:
    if not relative_path or not _SAFE_NAME.match(relative_path):
        return
    target = root / relative_path
    try:
        if target.resolve().parent != root.resolve():
            return
        target.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Screenshot delete failed (%s)", exc.__class__.__name__)


def delete_screenshots(root: Path, relative_paths: list[str | None]) -> None:
    for path in relative_paths:
        delete_screenshot(root, path)
