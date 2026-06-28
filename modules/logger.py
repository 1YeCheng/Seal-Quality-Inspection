from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .image_loader import save_image
from .models import BagInspectionResult


LOG_FIELDS = [
    "time", "bag_id", "img_2d", "img_ir", "time_diff_ms", "result_2d", "result_ir",
    "final_result", "ng_reason", "width", "height", "area", "angle", "temp_mean",
    "temp_std", "silver_area", "foreign_area", "io_ok", "io_ng", "io_reject",
]


class InspectionLogger:
    def __init__(self, log_dir: str | Path, ng_dir: str | Path, annotated_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.ng_dir = Path(ng_dir)
        self.annotated_dir = Path(annotated_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.ng_dir.mkdir(parents=True, exist_ok=True)
        self.annotated_dir.mkdir(parents=True, exist_ok=True)

    def append(self, result: BagInspectionResult) -> Path:
        log_path = self.log_dir / f"inspection_{datetime.now().strftime('%Y-%m-%d')}.csv"
        exists = log_path.exists()
        with log_path.open("a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(result.to_log_row())
        if result.final_result == "NG":
            self.save_ng_artifacts(result)
        return log_path

    def append_event(self, message: str) -> Path:
        """Save a human-readable runtime event log line locally."""
        log_path = self.log_dir / f"runtime_{datetime.now().strftime('%Y-%m-%d')}.txt"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
        return log_path

    def info(self, message: str) -> Path:
        return self.append_event(f"INFO {message}")

    def warning(self, message: str) -> Path:
        return self.append_event(f"WARN {message}")

    def error(self, message: str) -> Path:
        return self.append_event(f"ERROR {message}")

    def save_ng_artifacts(self, result: BagInspectionResult) -> Path:
        date_dir = self.ng_dir / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        bag_id = result.pair.bag_id

        if result.result_2d.raw_image is not None:
            save_image(date_dir / f"{bag_id}_2D_raw.jpg", result.result_2d.raw_image)
        if result.result_2d.annotated_image is not None:
            save_image(date_dir / f"{bag_id}_2D_annotated.jpg", result.result_2d.annotated_image)
            save_image(self.annotated_dir / f"{bag_id}_2D_annotated.jpg", result.result_2d.annotated_image)
        if result.result_ir.raw_image is not None:
            save_image(date_dir / f"{bag_id}_IR_raw.jpg", result.result_ir.raw_image)
        if result.result_ir.annotated_image is not None:
            save_image(date_dir / f"{bag_id}_IR_annotated.jpg", result.result_ir.annotated_image)
            save_image(self.annotated_dir / f"{bag_id}_IR_annotated.jpg", result.result_ir.annotated_image)

        json_path = date_dir / f"{bag_id}_result.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        return date_dir

    def read_logs(self) -> List[dict]:
        rows: List[dict] = []
        for path in sorted(self.log_dir.glob("inspection_*.csv")):
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                rows.extend(csv.DictReader(f))
        return rows

    def read_events(self, limit: int = 500) -> List[str]:
        lines: List[str] = []
        for path in sorted(self.log_dir.glob("runtime_*.txt")):
            with path.open("r", encoding="utf-8") as f:
                lines.extend(line.rstrip("\n") for line in f)
        return lines[-limit:]

    def list_ng_json(self) -> List[Path]:
        return sorted(self.ng_dir.glob("*/*_result.json"), reverse=True)
