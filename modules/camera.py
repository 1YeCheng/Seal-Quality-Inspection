from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from .timestamp_parser import parse_timestamp


class CameraState(Enum):
    DISCONNECTED = "disconnected"
    CONFIGURED = "configured"
    STREAMING = "streaming"


class SearchMode(Enum):
    BY_INDEX = "by_index"
    BY_SN = "by_sn"
    BY_NAME = "by_name"


class CaptureMode:
    CONTINUOUS = "continuous"
    SOFTWARE = "software"
    HARDWARE = "hardware"


class BaseCamera(ABC):
    def __init__(self, search_key: Any = 0, search_mode: SearchMode = SearchMode.BY_INDEX):
        self.search_key = search_key
        self.search_mode = search_mode
        self._state = CameraState.DISCONNECTED
        self._handle = None
        self._width = 0
        self._height = 0

    @property
    def state(self) -> CameraState:
        return self._state

    @abstractmethod
    def open(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def configure(self, params: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def start_grabbing(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def grab(self, timeout_ms=1000):
        raise NotImplementedError

    @abstractmethod
    def stop_grabbing(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> bool:
        raise NotImplementedError

    def _update_state(self, new_state: CameraState) -> None:
        self._state = new_state


class FileCamera(BaseCamera):
    """Folder-backed camera used to simulate an industrial camera stream."""

    def __init__(
        self,
        folder_path: str | Path,
        search_key: int = 0,
        search_mode: SearchMode = SearchMode.BY_INDEX,
        logger=None,
        camera_id: str = "FILE",
        loop: bool = True,
        interval_ms: int = 120,
    ):
        super().__init__(search_key, search_mode)
        self.camera_id = camera_id
        self.logger = logger
        self.folder_path = Path(folder_path)
        self.loop = loop
        self.interval_ms = interval_ms
        self.file_list: List[Path] = []
        self.idx = 0
        self.lock = threading.Lock()
        self.capture_mode = CaptureMode.CONTINUOUS
        self._frame_id = 0

    def open(self) -> bool:
        if self._state != CameraState.DISCONNECTED:
            return False
        if not self.folder_path.exists():
            self._log("error", f"[{self.camera_id}] 文件夹不存在: {self.folder_path}")
            return False

        exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        self.file_list = sorted(
            [p for p in self.folder_path.iterdir() if p.is_file() and p.suffix.lower() in exts],
            key=lambda p: p.name.lower(),
        )
        if not self.file_list:
            self._log("error", f"[{self.camera_id}] 文件夹中没有图像: {self.folder_path}")
            return False

        self.idx = 0
        self._frame_id = 0
        self._update_state(CameraState.CONFIGURED)
        self._log("info", f"[{self.camera_id}] FileCamera opened, {len(self.file_list)} images found")
        return True

    def configure(self, params: Dict[str, Any]) -> bool:
        if self._state not in [CameraState.CONFIGURED, CameraState.STREAMING]:
            return False
        if "interval_ms" in params:
            self.interval_ms = int(params["interval_ms"])
        if "loop" in params:
            self.loop = bool(params["loop"])
        return True

    def start_grabbing(self) -> bool:
        if self._state == CameraState.CONFIGURED:
            self._update_state(CameraState.STREAMING)
            self._log("info", f"[{self.camera_id}] streaming started")
            return True
        return False

    def grab(self, timeout_ms=1000):
        if self._state != CameraState.STREAMING:
            return None
        try:
            with self.lock:
                if not self.file_list:
                    return None
                file_path = self.file_list[self.idx]
                img = self._imread_safe(file_path)
                if img is None:
                    self._advance()
                    return None
                self._advance()
                self._frame_id += 1
                frame_id = self._frame_id

            timestamp = self._timestamp_from_file(file_path)
            time.sleep(max(0, self.interval_ms) / 1000.0)
            return {
                "camera_id": self.camera_id,
                "frame": img,
                "color_img": img,
                "timestamp": timestamp,
                "frame_id": frame_id,
                "file_path": str(file_path),
                "extra": {"color_img": img, "file_path": str(file_path)},
            }
        except Exception as exc:
            self._log("error", f"[{self.camera_id}] Grab error: {exc}")
            return None

    def stop_grabbing(self) -> bool:
        if self._state == CameraState.STREAMING:
            self._update_state(CameraState.CONFIGURED)
            self._log("info", f"[{self.camera_id}] streaming stopped")
        return True

    def close(self) -> bool:
        if self._state != CameraState.DISCONNECTED:
            self.stop_grabbing()
            self.file_list = []
            self.idx = 0
            self._frame_id = 0
            self._update_state(CameraState.DISCONNECTED)
            self._log("info", f"[{self.camera_id}] camera closed")
        return True

    def get_frame(self, timeout_ms=1000):
        result = self.grab(timeout_ms)
        return None if result is None else result["frame"]

    def set_acquisition_mode(self, mode, trigger_source="Line0") -> None:
        self.capture_mode = mode

    def set_camera_params(self, exposure=None, gain=None, frame_rate=None) -> None:
        if frame_rate:
            self.interval_ms = max(1, int(1000 / float(frame_rate)))

    def _advance(self) -> None:
        self.idx += 1
        if self.idx >= len(self.file_list):
            self.idx = 0 if self.loop else len(self.file_list) - 1

    def _imread_safe(self, path: Path):
        try:
            data = np.fromfile(str(path), dtype=np.uint8)
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception as exc:
            self._log("error", f"[{self.camera_id}] 读取异常: {path}, {exc}")
            return None

    @staticmethod
    def _timestamp_from_file(path: Path) -> float:
        timestamp = parse_timestamp(path, fallback_to_mtime=False)
        return time.time() if timestamp is None else timestamp.timestamp()

    def _log(self, level: str, message: str) -> None:
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(message)
