from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict


APP_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_CONFIG: Dict[str, Any] = {
    "ir": {
        "roi": [20, 40, 360, 120],
        "segmentation_mode": "pseudocolor",
        "threshold_mode": "otsu",
        "fixed_threshold": 140,
        "pseudocolor_hsv_ranges": [
            [0, 35, 80, 255, 80, 255],
            [160, 179, 80, 255, 80, 255]
        ],
        "min_width": 20,
        "max_width": 2000,
        "min_height": 5,
        "max_height": 1000,
        "min_area": 100,
        "max_area": 1000000,
        "max_angle": 8.0,
        "max_boundary_roughness": 0.35,
        "temp_min": 35.0,
        "temp_max": 220.0,
        "max_temp_std": 35.0,
        "min_seal_aspect_ratio": 3.0,
        "gray_min": 0,
        "gray_max": 255,
        "calib_temp_min": 20.0,
        "calib_temp_max": 180.0,
    },
    "visible": {
        "roi_mode": "auto",
        "roi": [250, 385, 800, 90],
        "roi_by_size": {
            "1280x1024": [250, 385, 800, 90],
            "2448x2048": [300, 1450, 1500, 170],
        },
        "auto_roi_search_by_size": {
            "1280x1024": [0.28, 0.56],
            "2448x2048": [0.62, 0.82],
        },
        "package_body_roi_enabled": True,
        "seal_search_in_body_by_size": {
            "1280x1024": [0.24, 0.66],
            "2448x2048": [0.25, 0.78],
        },
        "seal_search_in_body_ratio": [0.25, 0.78],
        "package_body_min_saturation": 35,
        "package_body_min_value": 35,
        "package_body_min_lab_a": 135,
        "package_body_min_lab_b": 138,
        "package_body_ignore_top_ratio": 0.18,
        "package_body_min_area_ratio": 0.01,
        "package_body_min_width_ratio": 0.25,
        "package_body_min_height_ratio": 0.05,
        "auto_roi_x_by_size": {
            "1280x1024": [0.20, 0.90],
            "2448x2048": [0.05, 0.78],
        },
        "auto_roi_search_ratio": [0.25, 0.90],
        "auto_roi_height_ratio": 0.085,
        "auto_roi_min_width_ratio": 0.45,
        "auto_roi_max_width_ratio": 0.82,
        "auto_roi_max_width_by_size": {
            "2448x2048": 0.62,
        },
        "auto_roi_min_edge_score": 8.0,
        "silver_v_threshold": 215,
        "silver_s_threshold": 60,
        "max_silver_area": 2500,
        "max_silver_ratio": 0.03,
        "foreign_std_factor": 2.6,
        "max_foreign_area": 500,
        "min_defect_area": 20,
        "min_width": 20,
        "max_width": 2000,
        "min_height": 5,
        "max_height": 1000,
    },
    "pairing": {
        "max_time_diff_ms": 500,
        "folder_2d": "data/paired_2D",
        "folder_ir": "data/paired_IR",
        "visible_prefixes": ["2D"],
        "ir_prefixes": ["IR"],
        "pair_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"],
    },
    "save": {
        "ng_image_dir": "result/NG_images",
        "annotated_dir": "result/annotated",
        "log_dir": "result/logs",
        "log_keep_days": 30,
        "auto_export_logs": True,
    },
    "io": {
        "simulate": True,
        "ok_signal": "OK",
        "ng_signal": "NG",
        "alarm_signal": "ALARM",
        "reject_signal": "REJECT",
        "reject_duration_ms": 120,
    },
    "runtime": {
        "poll_interval_ms": 1000,
    },
}


class ConfigManager:
    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else APP_ROOT / "config.json"
        self.config: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with self.config_path.open("r", encoding="utf-8") as f:
                user_config = json.load(f)
            self.config = self._deep_merge(copy.deepcopy(DEFAULT_CONFIG), user_config)
        else:
            self.save()
        return self.config

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get(self, section: str, default: Any = None) -> Any:
        return self.config.get(section, default)

    def update_from_json_text(self, text: str) -> None:
        data = json.loads(text)
        self.config = self._deep_merge(copy.deepcopy(DEFAULT_CONFIG), data)
        self.save()

    def to_json_text(self) -> str:
        return json.dumps(self.config, ensure_ascii=False, indent=2)

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return APP_ROOT / path

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = ConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value
        return base
