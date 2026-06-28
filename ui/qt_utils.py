from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel


def ndarray_to_pixmap(image: Optional[np.ndarray], max_width: int = 640, max_height: int = 420) -> QPixmap:
    if image is None:
        pixmap = QPixmap(max_width, max_height)
        pixmap.fill(Qt.darkGray)
        return pixmap

    if image.ndim == 2:
        rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    else:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
    pixmap = QPixmap.fromImage(qimg)
    return pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def set_image(label: QLabel, image: Optional[np.ndarray]) -> None:
    label.setPixmap(ndarray_to_pixmap(image, label.width() or 640, label.height() or 420))
    label.setAlignment(Qt.AlignCenter)

