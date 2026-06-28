from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class DetectionResult:
    source: str
    result: str = "OK"
    features: Dict[str, Any] = field(default_factory=dict)
    ng_reasons: List[str] = field(default_factory=list)
    annotated_image: Optional[np.ndarray] = None
    raw_image: Optional[np.ndarray] = None
    mask: Optional[np.ndarray] = None
    image_path: Optional[Path] = None

    def is_ok(self) -> bool:
        return self.result == "OK"

    def is_ng(self) -> bool:
        return self.result == "NG"

    def add_reason(self, reason: str) -> None:
        if reason and reason not in self.ng_reasons:
            self.ng_reasons.append(reason)
        self.result = "NG"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "result": self.result,
            "features": self.features,
            "ng_reasons": self.ng_reasons,
            "image_path": str(self.image_path) if self.image_path else "",
        }


@dataclass
class PairRecord:
    bag_id: str
    image_2d_path: Optional[Path]
    image_ir_path: Optional[Path]
    timestamp_2d: Optional[datetime]
    timestamp_ir: Optional[datetime]
    time_diff_ms: Optional[float]
    status: str = "PAIRED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bag_id": self.bag_id,
            "image_2d_path": str(self.image_2d_path) if self.image_2d_path else "",
            "image_ir_path": str(self.image_ir_path) if self.image_ir_path else "",
            "timestamp_2d": self.timestamp_2d.isoformat() if self.timestamp_2d else "",
            "timestamp_ir": self.timestamp_ir.isoformat() if self.timestamp_ir else "",
            "time_diff_ms": self.time_diff_ms,
            "status": self.status,
        }


@dataclass
class BagInspectionResult:
    pair: PairRecord
    result_2d: DetectionResult
    result_ir: DetectionResult
    final_result: str
    ng_reasons: List[str]
    io_state: Dict[str, Any] = field(default_factory=dict)
    inspected_at: datetime = field(default_factory=datetime.now)

    def to_log_row(self) -> Dict[str, Any]:
        features_2d = self.result_2d.features
        features_ir = self.result_ir.features
        return {
            "time": self.inspected_at.strftime("%Y-%m-%d %H:%M:%S"),
            "bag_id": self.pair.bag_id,
            "img_2d": self.pair.image_2d_path.name if self.pair.image_2d_path else "",
            "img_ir": self.pair.image_ir_path.name if self.pair.image_ir_path else "",
            "time_diff_ms": "" if self.pair.time_diff_ms is None else round(self.pair.time_diff_ms, 2),
            "result_2d": self.result_2d.result,
            "result_ir": self.result_ir.result,
            "final_result": self.final_result,
            "ng_reason": "; ".join(self.ng_reasons),
            "width": features_ir.get("width", features_2d.get("width", "")),
            "height": features_ir.get("height", features_2d.get("height", "")),
            "area": features_ir.get("area", features_2d.get("area", "")),
            "angle": features_ir.get("angle", ""),
            "temp_mean": features_ir.get("temp_mean", ""),
            "temp_std": features_ir.get("temp_std", ""),
            "silver_area": features_2d.get("silver_area", ""),
            "foreign_area": features_2d.get("foreign_area", ""),
            "io_ok": self.io_state.get("ok_signal", False),
            "io_ng": self.io_state.get("ng_signal", False),
            "io_reject": self.io_state.get("reject_triggered", False),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair": self.pair.to_dict(),
            "result_2d": self.result_2d.to_dict(),
            "result_ir": self.result_ir.to_dict(),
            "final_result": self.final_result,
            "ng_reasons": self.ng_reasons,
            "io_state": self.io_state,
            "inspected_at": self.inspected_at.isoformat(),
        }

