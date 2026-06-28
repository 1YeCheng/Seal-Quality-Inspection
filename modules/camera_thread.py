from __future__ import annotations

import time

from PyQt5.QtCore import QThread, pyqtSignal


class CameraThread(QThread):
    """Industrial-style camera grabbing thread adapted from reference_code."""

    packet_signal = pyqtSignal(dict)
    status_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(
        self,
        camera,
        camera_id: str = "RGB",
        timeout_ms: int = 1000,
        reconnect_interval: float = 1.0,
        max_reconnect_attempts: int = 5,
        logger=None,
    ):
        super().__init__()
        self.camera = camera
        self.camera_id = camera_id
        self.timeout_ms = timeout_ms
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.logger = logger
        self.running = False
        self._should_exit = False

    def start_capture(self) -> None:
        self.running = True

    def pause_capture(self) -> None:
        self.running = False

    def stop(self) -> None:
        self._should_exit = True
        self.running = False
        self._log("info", f"[{self.camera_id}] stop requested")

    def run(self) -> None:
        if self.camera is None:
            self._emit_error(f"[{self.camera_id}] camera object is empty")
            return

        try:
            if not self.camera.open():
                self._emit_error(f"[{self.camera_id}] failed to open camera")
                return
            if not self.camera.start_grabbing():
                self._emit_error(f"[{self.camera_id}] failed to start grabbing")
                self.camera.close()
                return
        except Exception as exc:
            self._emit_error(f"[{self.camera_id}] camera init error: {exc}")
            return

        self.status_signal.emit(f"[{self.camera_id}] camera started")

        while not self._should_exit:
            if not self.running:
                self.msleep(30)
                continue

            try:
                data = self.camera.grab(self.timeout_ms)
                if data is None:
                    continue

                packet = {
                    "camera_id": self.camera_id,
                    "frame": data.get("frame"),
                    "timestamp": data.get("timestamp", 0),
                    "frame_id": data.get("frame_id", 0),
                    "file_path": data.get("file_path", ""),
                    "extra": data.get("extra", {}),
                }
                if "color_img" in data:
                    packet["color_img"] = data["color_img"]
                self.packet_signal.emit(packet)

            except Exception as exc:
                self._log("error", f"[{self.camera_id}] grab error: {exc}")
                if not self._try_reconnect():
                    self._emit_error(f"[{self.camera_id}] reconnect failed, thread exits")
                    break
                time.sleep(self.reconnect_interval)

        self._cleanup()
        self.status_signal.emit(f"[{self.camera_id}] camera thread exited")

    def _try_reconnect(self) -> bool:
        attempts = 0
        while attempts < self.max_reconnect_attempts and not self._should_exit:
            try:
                if hasattr(self.camera, "reconnect") and self.camera.reconnect():
                    return True
            except Exception:
                pass
            attempts += 1
            time.sleep(self.reconnect_interval)
        return False

    def _cleanup(self) -> None:
        try:
            if hasattr(self.camera, "stop_grabbing"):
                self.camera.stop_grabbing()
        except Exception as exc:
            self._log("error", f"[{self.camera_id}] stop_grabbing error: {exc}")
        try:
            if hasattr(self.camera, "close"):
                self.camera.close()
        except Exception as exc:
            self._log("error", f"[{self.camera_id}] close error: {exc}")

    def _emit_error(self, message: str) -> None:
        self._log("error", message)
        self.error_signal.emit(message)

    def _log(self, level: str, message: str) -> None:
        if self.logger and hasattr(self.logger, level):
            getattr(self.logger, level)(message)
