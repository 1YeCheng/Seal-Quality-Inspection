from __future__ import annotations

from pathlib import Path
from typing import Dict

import cv2
import numpy as np

from .feature_extractor import contour_geometry, crop_roi, draw_roi, gray_to_temperature, largest_contour
from .image_loader import ensure_bgr, read_image
from .models import DetectionResult


class IRDetector:
    def __init__(self, config: Dict):
        self.config = config

    def detect_path(self, path: str | Path) -> DetectionResult:
        image = read_image(path, cv2.IMREAD_UNCHANGED)
        if image is None:
            result = DetectionResult(source="IR", result="NG", image_path=Path(path))
            result.add_reason("红外图像读取失败")
            return result
        result = self.detect(image)
        result.image_path = Path(path)
        return result

    def detect(self, image: np.ndarray) -> DetectionResult:
        raw_bgr = ensure_bgr(image)
        annotated = raw_bgr.copy()
        roi_img, roi = crop_roi(raw_bgr, self.config.get("roi", [0, 0, 0, 0]))

        gray_raw = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY) if roi_img.ndim == 3 else roi_img.copy()
        gray = cv2.GaussianBlur(gray_raw, (5, 5), 0)
        gray = cv2.medianBlur(gray, 3)
        mask = self._segment_roi(roi_img, gray)

        contour = self._select_seal_contour(mask)
        result = DetectionResult(source="IR", raw_image=raw_bgr, annotated_image=annotated, mask=mask)
        if contour is None or cv2.contourArea(contour) <= 0:
            result.add_reason("红外封口区域未定位")
            cv2.putText(annotated, "NG", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            result.annotated_image = annotated
            return result

        features = contour_geometry(contour)
        contour_mask = np.zeros_like(mask)
        cv2.drawContours(contour_mask, [contour], -1, 255, -1)
        selected_gray = gray[contour_mask > 0]
        temps = gray_to_temperature(selected_gray, self.config)
        features.update({
            "temp_mean": round(float(np.mean(temps)), 2),
            "temp_max": round(float(np.max(temps)), 2),
            "temp_min": round(float(np.min(temps)), 2),
            "temp_std": round(float(np.std(temps)), 2),
            "temp_range": round(float(np.max(temps) - np.min(temps)), 2),
            "segmentation_mode": self.config.get("segmentation_mode", "pseudocolor"),
        })
        result.features = features

        display_contour = self._display_contour(contour)
        offset_contour = display_contour + np.array([[[roi[0], roi[1]]]])
        cv2.drawContours(annotated, [offset_contour], -1, (0, 255, 0), 2)
        cv2.putText(annotated, "IR", (roi[0] + 8, roi[1] + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        self._apply_rules(result)
        if result.is_ng():
            cv2.putText(annotated, "NG", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        else:
            cv2.putText(annotated, "OK", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 180, 0), 3)
        result.annotated_image = annotated
        return result

    def _segment_roi(self, roi_img: np.ndarray, gray: np.ndarray) -> np.ndarray:
        mode = self.config.get("segmentation_mode", "pseudocolor")
        if mode == "pseudocolor" and roi_img.ndim == 3:
            mask = self._segment_pseudocolor(roi_img)
            if cv2.countNonZero(mask) > 0:
                return mask
        return self._segment_gray(gray)

    def _segment_gray(self, gray: np.ndarray) -> np.ndarray:
        if self.config.get("threshold_mode", "otsu") == "fixed":
            _, mask = cv2.threshold(gray, int(self.config.get("fixed_threshold", 140)), 255, cv2.THRESH_BINARY)
        else:
            _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return self._clean_mask(mask)

    def _segment_pseudocolor(self, roi_img: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        ranges = self.config.get("pseudocolor_hsv_ranges", [])
        for item in ranges:
            if len(item) != 6:
                continue
            h_min, h_max, s_min, s_max, v_min, v_max = [int(v) for v in item]
            lower = np.array([h_min, s_min, v_min], dtype=np.uint8)
            upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))
        return self._clean_mask(mask)

    @staticmethod
    def _clean_mask(mask: np.ndarray) -> np.ndarray:
        kernel = np.ones((5, 5), np.uint8)
        horizontal_kernel = np.ones((5, 31), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, horizontal_kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        return mask

    def _select_seal_contour(self, mask: np.ndarray):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        h, w = mask.shape[:2]
        candidates = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area <= 0:
                continue
            x, y, bw, bh = cv2.boundingRect(contour)
            aspect = bw / max(float(bh), 1.0)
            fill_ratio = area / max(float(bw * bh), 1.0)
            if bw < w * 0.25 or bh < h * 0.03:
                continue
            if aspect < float(self.config.get("min_seal_aspect_ratio", 3.0)):
                continue
            score = area * aspect * max(fill_ratio, 0.2)
            candidates.append((score, contour))

        if candidates:
            return max(candidates, key=lambda item: item[0])[1]
        return self._contour_from_hot_band(mask)

    @staticmethod
    def _display_contour(contour):
        rect = cv2.minAreaRect(contour)
        return cv2.boxPoints(rect).astype(np.int32).reshape(-1, 1, 2)

    @staticmethod
    def _contour_from_hot_band(mask: np.ndarray):
        h, w = mask.shape[:2]
        row_counts = np.count_nonzero(mask, axis=1).astype(np.float32)
        if float(np.max(row_counts)) < max(8.0, w * 0.08):
            return None
        smooth_len = max(7, int(h * 0.04))
        if smooth_len % 2 == 0:
            smooth_len += 1
        row_counts = np.convolve(row_counts, np.ones(smooth_len) / smooth_len, mode="same")
        center_y = int(np.argmax(row_counts))
        band_h = max(12, int(h * 0.22))
        y0 = max(0, center_y - band_h // 2)
        y1 = min(h, center_y + band_h // 2)
        ys, xs = np.where(mask[y0:y1] > 0)
        if len(xs) == 0:
            return None
        x0 = int(np.min(xs))
        x1 = int(np.max(xs))
        yy0 = y0 + int(np.min(ys))
        yy1 = y0 + int(np.max(ys))
        if x1 - x0 < w * 0.20:
            return None
        points = np.array(
            [[[x0, yy0]], [[x1, yy0]], [[x1, yy1]], [[x0, yy1]]],
            dtype=np.int32,
        )
        return points

    def _apply_rules(self, result: DetectionResult) -> None:
        f = result.features
        checks = [
            ("红外封口宽度异常", f.get("width", 0), self.config.get("min_width", 0), self.config.get("max_width", 10**9)),
            ("红外封口高度异常", f.get("height", 0), self.config.get("min_height", 0), self.config.get("max_height", 10**9)),
            ("红外封口面积异常", f.get("area", 0), self.config.get("min_area", 0), self.config.get("max_area", 10**12)),
            ("红外封口温度均值异常", f.get("temp_mean", 0), self.config.get("temp_min", -10**9), self.config.get("temp_max", 10**9)),
        ]
        for label, value, low, high in checks:
            if value < low or value > high:
                result.add_reason(f"{label}: {value} 不在 [{low}, {high}]")
        if f.get("angle", 0) > float(self.config.get("max_angle", 8.0)):
            result.add_reason(f"红外封口倾斜异常: {f.get('angle')} > {self.config.get('max_angle')}")
        if f.get("boundary_roughness", 0) > float(self.config.get("max_boundary_roughness", 0.35)):
            result.add_reason(f"红外边界不平滑: {f.get('boundary_roughness')} > {self.config.get('max_boundary_roughness')}")
        if f.get("temp_std", 0) > float(self.config.get("max_temp_std", 35.0)):
            result.add_reason(f"红外温度不均匀: {f.get('temp_std')} > {self.config.get('max_temp_std')}")
