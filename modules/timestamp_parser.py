from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional


TIMESTAMP_PATTERNS = [
    re.compile(r"(?P<date>\d{8})[_-](?P<time>\d{6})[_-](?P<ms>\d{1,6})"),
    re.compile(r"(?P<date>\d{8})(?P<time>\d{6})(?P<ms>\d{1,6})"),
]

CAMERA_CLOCK_PATTERN = re.compile(
    r"(?:[A-Z])?Camera(?P<hour>\d{2})-(?P<minute>\d{2})-(?P<second>\d{2})-(?P<ms>\d{1,6})",
    re.IGNORECASE,
)


def parse_timestamp(path: str | Path, fallback_to_mtime: bool = True) -> Optional[datetime]:
    path = Path(path)
    stem = path.stem
    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        date_part = match.group("date")
        time_part = match.group("time")
        ms_part = match.group("ms")[:6].ljust(6, "0")
        try:
            return datetime.strptime(f"{date_part}{time_part}{ms_part}", "%Y%m%d%H%M%S%f")
        except ValueError:
            continue

    camera_match = CAMERA_CLOCK_PATTERN.search(stem)
    if camera_match:
        try:
            hour = int(camera_match.group("hour")) % 12
            minute = int(camera_match.group("minute"))
            second = int(camera_match.group("second"))
            microsecond = int(camera_match.group("ms")[:6].ljust(6, "0"))
            return datetime(2000, 1, 1, hour, minute, second, microsecond)
        except ValueError:
            pass

    if fallback_to_mtime and path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime)
    return None


def diff_ms(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds() * 1000.0)
