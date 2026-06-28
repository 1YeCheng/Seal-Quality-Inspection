from __future__ import annotations

from typing import Dict, List, Tuple

import cv2
import numpy as np


def crop_roi(image: np.ndarray, roi: List[int] | Tuple[int, int, int, int]) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    h, w = image.shape[:2]
    x, y, rw, rh = [int(v) for v in roi]
    if rw <= 0 or rh <= 0:
        return image.copy(), (0, 0, w, h)
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    rw = max(1, min(rw, w - x))
    rh = max(1, min(rh, h - y))
    return image[y:y + rh, x:x + rw].copy(), (x, y, rw, rh)


def largest_contour(mask: np.ndarray):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def connected_component_stats(mask: np.ndarray, min_area: int = 1) -> Dict[str, float]:
    labels, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    areas = []
    for i in range(1, labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area >= min_area:
            areas.append(area)
    return {
        "count": len(areas),
        "total_area": int(sum(areas)),
        "max_area": int(max(areas) if areas else 0),
    }


def contour_geometry(contour) -> Dict[str, float]:
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    x, y, w, h = cv2.boundingRect(contour)
    rect = cv2.minAreaRect(contour)
    angle = float(rect[2])
    if angle < -45:
        angle += 90
    if angle > 45:
        angle -= 90
    rect_area = max(float(rect[1][0] * rect[1][1]), 1.0)
    roughness = perimeter / max(2.0 * (w + h), 1.0) - 1.0
    fill_ratio = area / rect_area
    return {
        "area": round(area, 2),
        "perimeter": round(perimeter, 2),
        "width": int(w),
        "height": int(h),
        "x": int(x),
        "y": int(y),
        "angle": round(abs(angle), 2),
        "boundary_roughness": round(max(0.0, roughness), 4),
        "fill_ratio": round(fill_ratio, 4),
    }


def gray_to_temperature(gray_values: np.ndarray, config: Dict) -> np.ndarray:
    gray_min = float(config.get("gray_min", 0))
    gray_max = float(config.get("gray_max", 255))
    temp_min = float(config.get("calib_temp_min", 20.0))
    temp_max = float(config.get("calib_temp_max", 180.0))
    denom = max(gray_max - gray_min, 1e-6)
    return temp_min + (gray_values.astype(np.float32) - gray_min) * (temp_max - temp_min) / denom


def draw_roi(image: np.ndarray, roi: Tuple[int, int, int, int], color=(255, 200, 0)) -> None:
    x, y, w, h = roi
    cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
