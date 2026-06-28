from __future__ import annotations

from typing import List

from .models import BagInspectionResult, DetectionResult, PairRecord


def combine_results(pair: PairRecord, visible: DetectionResult, ir: DetectionResult, io_state=None) -> BagInspectionResult:
    reasons: List[str] = []
    if pair.status != "PAIRED":
        reasons.append("图像配对失败或单模态图像缺失")
    for result in (visible, ir):
        for reason in result.ng_reasons:
            prefix = result.source
            reasons.append(f"[{prefix}] {reason}")
    final = "OK" if pair.status == "PAIRED" and visible.is_ok() and ir.is_ok() else "NG"
    return BagInspectionResult(pair, visible, ir, final, reasons, io_state or {})

