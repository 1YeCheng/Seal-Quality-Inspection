from __future__ import annotations

from pathlib import Path
from typing import Dict

import cv2
import numpy as np

from .feature_extractor import connected_component_stats, crop_roi, draw_roi
from .image_loader import ensure_bgr, read_image
from .models import DetectionResult


class VisibleDetector:
    def __init__(self, config: Dict):
        self.config = config

    def detect_path(self, path: str | Path) -> DetectionResult:
        image = read_image(path, cv2.IMREAD_COLOR)
        if image is None:
            result = DetectionResult(source="2D", result="NG", image_path=Path(path))
            result.add_reason("2D图像读取失败")
            return result
        result = self.detect(image)
        result.image_path = Path(path)
        return result

    def detect(self, image: np.ndarray) -> DetectionResult:
        raw_bgr = ensure_bgr(image)
        annotated = raw_bgr.copy()
        roi_img, roi = crop_roi(raw_bgr, self._select_roi(raw_bgr))
        draw_roi(annotated, roi)

        filtered = cv2.GaussianBlur(roi_img, (5, 5), 0)
        hsv = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]

        silver_mask = ((v >= int(self.config.get("silver_v_threshold", 190))) &
                       (s <= int(self.config.get("silver_s_threshold", 70)))).astype(np.uint8) * 255
        kernel = np.ones((3, 3), np.uint8)
        silver_mask = cv2.morphologyEx(silver_mask, cv2.MORPH_OPEN, kernel)
        silver_mask = cv2.morphologyEx(silver_mask, cv2.MORPH_CLOSE, kernel)

        gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
        mean = float(np.mean(gray))
        std = float(np.std(gray))
        factor = float(self.config.get("foreign_std_factor", 2.6))
        foreign_mask = (np.abs(gray.astype(np.float32) - mean) > factor * max(std, 1.0)).astype(np.uint8) * 255
        foreign_mask[silver_mask > 0] = 0
        foreign_mask = cv2.morphologyEx(foreign_mask, cv2.MORPH_OPEN, kernel)

        min_defect_area = int(self.config.get("min_defect_area", 20))
        silver_stats = connected_component_stats(silver_mask, min_defect_area)
        foreign_stats = connected_component_stats(foreign_mask, min_defect_area)
        roi_area = max(roi[2] * roi[3], 1)

        features = {
            "width": roi[2],
            "height": roi[3],
            "silver_area": silver_stats["total_area"],
            "silver_max_area": silver_stats["max_area"],
            "silver_count": silver_stats["count"],
            "silver_ratio": round(silver_stats["total_area"] / roi_area, 5),
            "foreign_area": foreign_stats["total_area"],
            "foreign_max_area": foreign_stats["max_area"],
            "foreign_count": foreign_stats["count"],
            "gray_mean": round(mean, 2),
            "gray_std": round(std, 2),
        }

        silver_overlay = np.zeros_like(roi_img)
        silver_overlay[silver_mask > 0] = (230, 230, 230)
        foreign_overlay = np.zeros_like(roi_img)
        foreign_overlay[foreign_mask > 0] = (0, 0, 255)
        roi_annotated = cv2.addWeighted(roi_img, 0.7, silver_overlay, 0.3, 0)
        roi_annotated = cv2.addWeighted(roi_annotated, 0.75, foreign_overlay, 0.45, 0)
        annotated[roi[1]:roi[1] + roi[3], roi[0]:roi[0] + roi[2]] = roi_annotated
        cv2.putText(annotated, "2D", (roi[0] + 8, roi[1] + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        result = DetectionResult(
            source="2D",
            raw_image=raw_bgr,
            annotated_image=annotated,
            mask=cv2.bitwise_or(silver_mask, foreign_mask),
            features=features,
        )
        self._apply_rules(result)
        if result.is_ng():
            cv2.putText(annotated, "NG", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        else:
            cv2.putText(annotated, "OK", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 180, 0), 3)
        result.annotated_image = annotated
        return result

    def _select_roi(self, image: np.ndarray):
        if self.config.get("roi_mode", "auto") == "auto":
            roi = self._auto_locate_roi(image)
            if roi is not None:
                return roi
        h, w = image.shape[:2]
        roi_by_size = self.config.get("roi_by_size", {})
        size_key = f"{w}x{h}"
        if isinstance(roi_by_size, dict) and size_key in roi_by_size:
            return roi_by_size[size_key]
        return self.config.get("roi", [0, 0, 0, 0])

    def _auto_locate_roi(self, image: np.ndarray):
        h, w = image.shape[:2]
        size_key = f"{w}x{h}"
        body = self._locate_package_body(image) if self.config.get("package_body_roi_enabled", True) else None

        if body is not None:
            bx, by, bw, bh = body
            body_ranges = self.config.get("seal_search_in_body_by_size", {})
            y_range = body_ranges.get(size_key, self.config.get("seal_search_in_body_ratio", [0.25, 0.78]))
            x_ranges = self.config.get("auto_roi_x_by_size", {})
            x_range = x_ranges.get(size_key, self.config.get("auto_roi_x_ratio", [0.08, 0.92]))
            if not isinstance(y_range, list) or len(y_range) != 2:
                return None
            if not isinstance(x_range, list) or len(x_range) != 2:
                return None
            y0 = by + int(bh * float(y_range[0]))
            y1 = by + int(bh * float(y_range[1]))
            search_x0 = bx + int(bw * float(x_range[0]))
            search_x1 = bx + int(bw * float(x_range[1]))
        else:
            search_ranges = self.config.get("auto_roi_search_by_size", {})
            y_range = search_ranges.get(size_key, self.config.get("auto_roi_search_ratio", [0.25, 0.90]))
            if not isinstance(y_range, list) or len(y_range) != 2:
                return None
            y0 = int(h * float(y_range[0]))
            y1 = int(h * float(y_range[1]))
            x_ranges = self.config.get("auto_roi_x_by_size", {})
            x_range = x_ranges.get(size_key, [0.0, 1.0])
            search_x0 = int(w * float(x_range[0]))
            search_x1 = int(w * float(x_range[1]))

        y0 = max(0, min(y0, h - 2))
        y1 = max(y0 + 2, min(y1, h))
        search_x0 = max(0, min(search_x0, w - 1))
        search_x1 = max(search_x0 + 1, min(search_x1, w))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        search = gray[y0:y1, search_x0:search_x1]
        if search.size == 0:
            return None

        edge = np.abs(cv2.Sobel(search, cv2.CV_32F, 0, 1, ksize=3))
        row_score = edge.mean(axis=1)
        smooth_len = max(15, int(h * 0.015))
        if smooth_len % 2 == 0:
            smooth_len += 1
        row_score = np.convolve(row_score, np.ones(smooth_len) / smooth_len, mode="same")
        if float(np.max(row_score)) < float(self.config.get("auto_roi_min_edge_score", 8.0)):
            return None

        center_y = y0 + int(np.argmax(row_score))
        roi_h = int(h * float(self.config.get("auto_roi_height_ratio", 0.085)))
        roi_h = max(60, min(roi_h, int(h * 0.16)))
        y = max(0, min(center_y - roi_h // 2, h - roi_h))

        if body is not None:
            return [int(search_x0), int(y), int(search_x1 - search_x0), int(roi_h)]

        local_top = max(0, center_y - y0 - roi_h // 2)
        local_bottom = min(edge.shape[0], center_y - y0 + roi_h // 2)
        band_edge = edge[local_top:local_bottom]
        if band_edge.size == 0:
            return None

        col_score = band_edge.mean(axis=0)
        col_smooth_len = max(31, int(w * 0.02))
        col_score = np.convolve(col_score, np.ones(col_smooth_len) / col_smooth_len, mode="same")
        active = np.where(col_score > np.percentile(col_score, 60))[0]
        if len(active) == 0:
            x = int(w * 0.12)
            roi_w = int(w * 0.70)
        else:
            margin = int(w * 0.04)
            x = max(0, int(active[0]) - margin)
            roi_w = min(w - x, int(active[-1]) + margin - x)

        min_width_ratio = float(self.config.get("auto_roi_min_width_ratio", 0.45))
        max_width_by_size = self.config.get("auto_roi_max_width_by_size", {})
        max_width_ratio = float(max_width_by_size.get(size_key, self.config.get("auto_roi_max_width_ratio", 0.82)))
        min_w = int(w * min_width_ratio)
        max_w = int(w * max_width_ratio)
        if roi_w < min_w:
            center_x = x + roi_w // 2
            roi_w = min_w
            x = max(0, min(center_x - roi_w // 2, w - roi_w))
        if roi_w > max_w:
            roi_w = max_w
            x = max(0, min(x, w - roi_w))

        return [int(x), int(y), int(roi_w), int(roi_h)]

    def _locate_package_body(self, image: np.ndarray):
        h, w = image.shape[:2]
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        s = hsv[:, :, 1]
        v = hsv[:, :, 2]
        a = lab[:, :, 1]
        b = lab[:, :, 2]

        min_s = int(self.config.get("package_body_min_saturation", 35))
        min_v = int(self.config.get("package_body_min_value", 35))
        mask = (
            ((s > min_s) & (v > min_v)) |
            ((b > int(self.config.get("package_body_min_lab_b", 138))) & (v > min_v + 10)) |
            ((a > int(self.config.get("package_body_min_lab_a", 135))) & (v > min_v))
        ).astype(np.uint8) * 255
        mask[:int(h * float(self.config.get("package_body_ignore_top_ratio", 0.18))), :] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((35, 75), np.uint8), iterations=2)

        labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        candidates = []
        for index in range(1, labels):
            x, y, bw, bh, area = [int(value) for value in stats[index]]
            if area < h * w * float(self.config.get("package_body_min_area_ratio", 0.01)):
                continue
            if bw < w * float(self.config.get("package_body_min_width_ratio", 0.25)):
                continue
            if bh < h * float(self.config.get("package_body_min_height_ratio", 0.05)):
                continue
            score = area * (bw / max(w, 1)) * (1.0 + 0.3 * y / max(h, 1))
            candidates.append((score, x, y, bw, bh))
        if not candidates:
            return None
        _, x, y, bw, bh = max(candidates, key=lambda item: item[0])
        return x, y, bw, bh

    def _apply_rules(self, result: DetectionResult) -> None:
        f = result.features
        silver_area = f.get("silver_area", 0)
        silver_ratio = f.get("silver_ratio", 0)
        if silver_area > int(self.config.get("max_silver_area", 600)):
            result.add_reason(f"2D图像存在银边: 面积 {silver_area} > {self.config.get('max_silver_area')}")
        if silver_ratio > float(self.config.get("max_silver_ratio", 0.03)):
            result.add_reason(f"2D银边占比异常: {silver_ratio} > {self.config.get('max_silver_ratio')}")
