from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ROIImageWidget(QWidget):
    def __init__(self, image: np.ndarray, roi=None, parent=None):
        super().__init__(parent)
        self.image = image
        self.original_h, self.original_w = image.shape[:2]
        self.current_roi = self._normalize_roi(roi)
        self.drag_start: Optional[QPoint] = None
        self.drag_end: Optional[QPoint] = None
        self.pixmap = self._to_pixmap(image)
        self.scaled_rect = QRect()
        self.setMinimumSize(760, 480)

    def selected_roi(self) -> Tuple[int, int, int, int]:
        if self.drag_start is not None and self.drag_end is not None:
            rect = QRect(self.drag_start, self.drag_end).normalized()
            return self._widget_rect_to_image_roi(rect)
        return self.current_roi

    def reset_roi(self) -> None:
        self.current_roi = (0, 0, 0, 0)
        self.drag_start = None
        self.drag_end = None
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1f2429"))
        scaled = self.pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self.scaled_rect = QRect(x, y, scaled.width(), scaled.height())
        painter.drawPixmap(self.scaled_rect, scaled)

        roi = self.selected_roi()
        if roi[2] > 0 and roi[3] > 0:
            painter.setPen(QPen(QColor("#78ff5a"), 2))
            painter.drawRect(self._image_roi_to_widget_rect(roi))

        if self.drag_start is not None and self.drag_end is not None:
            painter.setPen(QPen(QColor("#ffd84d"), 2, Qt.DashLine))
            painter.drawRect(QRect(self.drag_start, self.drag_end).normalized())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.scaled_rect.contains(event.pos()):
            self.drag_start = self._clamp_to_scaled(event.pos())
            self.drag_end = self.drag_start
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.drag_start is not None:
            self.drag_end = self._clamp_to_scaled(event.pos())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.drag_start is not None:
            self.drag_end = self._clamp_to_scaled(event.pos())
            self.current_roi = self.selected_roi()
            self.update()

    def _clamp_to_scaled(self, point: QPoint) -> QPoint:
        x = max(self.scaled_rect.left(), min(point.x(), self.scaled_rect.right()))
        y = max(self.scaled_rect.top(), min(point.y(), self.scaled_rect.bottom()))
        return QPoint(x, y)

    def _widget_rect_to_image_roi(self, rect: QRect) -> Tuple[int, int, int, int]:
        if self.scaled_rect.width() <= 0 or self.scaled_rect.height() <= 0:
            return self.current_roi
        x1 = (rect.left() - self.scaled_rect.left()) / self.scaled_rect.width() * self.original_w
        y1 = (rect.top() - self.scaled_rect.top()) / self.scaled_rect.height() * self.original_h
        x2 = (rect.right() - self.scaled_rect.left()) / self.scaled_rect.width() * self.original_w
        y2 = (rect.bottom() - self.scaled_rect.top()) / self.scaled_rect.height() * self.original_h
        x = max(0, min(int(round(x1)), self.original_w - 1))
        y = max(0, min(int(round(y1)), self.original_h - 1))
        w = max(1, min(int(round(x2 - x1)), self.original_w - x))
        h = max(1, min(int(round(y2 - y1)), self.original_h - y))
        return (x, y, w, h)

    def _image_roi_to_widget_rect(self, roi) -> QRect:
        x, y, w, h = roi
        if w <= 0 or h <= 0 or self.scaled_rect.width() <= 0:
            x, y, w, h = 0, 0, self.original_w, self.original_h
        left = self.scaled_rect.left() + x / self.original_w * self.scaled_rect.width()
        top = self.scaled_rect.top() + y / self.original_h * self.scaled_rect.height()
        width = w / self.original_w * self.scaled_rect.width()
        height = h / self.original_h * self.scaled_rect.height()
        return QRect(int(left), int(top), int(width), int(height))

    def _normalize_roi(self, roi) -> Tuple[int, int, int, int]:
        if not roi or len(roi) != 4:
            return (0, 0, 0, 0)
        x, y, w, h = [int(v) for v in roi]
        if w <= 0 or h <= 0:
            return (0, 0, 0, 0)
        x = max(0, min(x, self.original_w - 1))
        y = max(0, min(y, self.original_h - 1))
        w = max(1, min(w, self.original_w - x))
        h = max(1, min(h, self.original_h - y))
        return (x, y, w, h)

    @staticmethod
    def _to_pixmap(image: np.ndarray) -> QPixmap:
        if image.ndim == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimg)


class ROIDialog(QDialog):
    def __init__(self, image: np.ndarray, roi=None, title="ROI设置", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 620)
        self.image_widget = ROIImageWidget(image, roi, self)
        self.info = QLabel("在图像中按住左键拖拽矩形区域，点击确定保存 ROI。")
        self.info.setStyleSheet("color:#dce4ec;")

        reset_btn = QPushButton("重置ROI")
        ok_btn = QPushButton("确定")
        cancel_btn = QPushButton("取消")
        reset_btn.clicked.connect(self.image_widget.reset_roi)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(reset_btn)
        buttons.addStretch(1)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.image_widget, 1)
        layout.addLayout(buttons)
        self.setStyleSheet(
            """
            QDialog, QWidget { background:#2f343a; color:#dce4ec; }
            QPushButton {
                background:#4b5562; color:#f0f4f8; border:1px solid #606a76;
                padding:8px 16px;
            }
            QPushButton:hover { background:#596575; }
            """
        )

    def roi(self) -> Tuple[int, int, int, int]:
        return self.image_widget.selected_roi()

