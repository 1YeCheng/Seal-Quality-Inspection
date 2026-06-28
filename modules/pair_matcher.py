from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .models import PairRecord
from .timestamp_parser import diff_ms, parse_timestamp


@dataclass
class TimedImage:
    path: Path
    timestamp: Optional[datetime]


class PairMatcher:
    def __init__(self, max_time_diff_ms: float = 1000.0):
        self.max_time_diff_ms = max_time_diff_ms

    def match(self, visible_files: List[Path], ir_files: List[Path]) -> List[PairRecord]:
        visible_items = self._timed_items(visible_files)
        ir_items = self._timed_items(ir_files)
        candidate_edges = []
        for vi, visible in enumerate(visible_items):
            if visible.timestamp is None:
                continue
            for ii, ir in enumerate(ir_items):
                if ir.timestamp is None:
                    continue
                current_diff = diff_ms(visible.timestamp, ir.timestamp)
                if current_diff <= self.max_time_diff_ms:
                    candidate_edges.append((current_diff, vi, ii))

        used_visible: set[int] = set()
        used_ir: set[int] = set()
        records = []
        for current_diff, vi, ii in sorted(candidate_edges, key=lambda edge: (edge[0], edge[1], edge[2])):
            if vi in used_visible or ii in used_ir:
                continue
            used_visible.add(vi)
            used_ir.add(ii)
            visible = visible_items[vi]
            ir = ir_items[ii]
            sort_time = min(visible.timestamp, ir.timestamp) if visible.timestamp and ir.timestamp else visible.timestamp or ir.timestamp
            records.append(
                (
                    sort_time,
                    PairRecord(
                        "",
                        visible.path,
                        ir.path,
                        visible.timestamp,
                        ir.timestamp,
                        current_diff,
                        "PAIRED",
                    ),
                )
            )

        for vi, visible in enumerate(visible_items):
            if vi in used_visible:
                continue
            records.append(
                (
                    visible.timestamp,
                    PairRecord("", visible.path, None, visible.timestamp, None, None, "UNPAIRED_2D"),
                )
            )

        for ii, ir in enumerate(ir_items):
            if ii in used_ir:
                continue
            records.append(
                (
                    ir.timestamp,
                    PairRecord("", None, ir.path, None, ir.timestamp, None, "UNPAIRED_IR"),
                )
            )

        records.sort(key=lambda item: (item[0] is None, item[0]))
        pairs = []
        for index, (_sort_time, record) in enumerate(records, start=1):
            record.bag_id = f"BAG{index:04d}"
            pairs.append(record)
        return pairs

    @staticmethod
    def _timed_items(files: List[Path]) -> List[TimedImage]:
        items = [TimedImage(path=p, timestamp=parse_timestamp(p)) for p in files]
        return sorted(items, key=lambda item: (item.timestamp is None, item.timestamp or item.path.stat().st_mtime, item.path.name))
