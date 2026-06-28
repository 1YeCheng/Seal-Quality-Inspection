from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from modules.image_loader import read_image
from modules.logger import InspectionLogger
from .qt_utils import set_image


class NGBrowser(QDialog):
    def __init__(self, logger: InspectionLogger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.setWindowTitle("NG 图像浏览与分析")
        self.resize(1180, 720)

        self.list_widget = QListWidget()
        self.list_widget.currentTextChanged.connect(self.load_item)

        self.image_2d = QLabel("2D标注图")
        self.image_ir = QLabel("红外标注图")
        for label in (self.image_2d, self.image_ir):
            label.setMinimumSize(420, 300)
            label.setStyleSheet("background:#20242a;color:#e6edf3;border:1px solid #3a4048;")
            label.setAlignment(Qt.AlignCenter)

        self.info = QTextEdit()
        self.info.setReadOnly(True)

        refresh_btn = QPushButton("刷新")
        open_btn = QPushButton("打开所在文件夹")
        close_btn = QPushButton("关闭")
        refresh_btn.clicked.connect(self.refresh)
        open_btn.clicked.connect(self.open_folder)
        close_btn.clicked.connect(self.accept)

        left = QVBoxLayout()
        left.addWidget(self.list_widget)
        left.addWidget(refresh_btn)
        left.addWidget(open_btn)
        left.addWidget(close_btn)

        images = QHBoxLayout()
        images.addWidget(self.image_2d)
        images.addWidget(self.image_ir)

        right = QVBoxLayout()
        right.addLayout(images)
        right.addWidget(self.info)

        layout = QHBoxLayout(self)
        layout.addLayout(left, 1)
        layout.addLayout(right, 4)
        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        for path in self.logger.list_ng_json():
            self.list_widget.addItem(str(path))

    def load_item(self, text: str) -> None:
        if not text:
            return
        path = Path(text)
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self.info.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))
            bag_id = data.get("pair", {}).get("bag_id", path.stem.replace("_result", ""))
            folder = path.parent
            set_image(self.image_2d, read_image(folder / f"{bag_id}_2D_annotated.jpg"))
            set_image(self.image_ir, read_image(folder / f"{bag_id}_IR_annotated.jpg"))
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", str(exc))

    def open_folder(self) -> None:
        current = self.list_widget.currentItem()
        if current:
            os.startfile(str(Path(current.text()).parent))

