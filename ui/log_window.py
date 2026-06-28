from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout

from modules.logger import LOG_FIELDS, InspectionLogger


class LogWindow(QDialog):
    def __init__(self, logger: InspectionLogger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.setWindowTitle("日志浏览与导出")
        self.resize(1180, 720)

        self.event_text = QTextEdit()
        self.event_text.setReadOnly(True)
        self.event_text.setStyleSheet("font-family: Consolas, Microsoft YaHei;")

        self.table = QTableWidget(0, len(LOG_FIELDS))
        self.table.setHorizontalHeaderLabels(LOG_FIELDS)
        self.table.horizontalHeader().setStretchLastSection(True)

        refresh_btn = QPushButton("刷新")
        close_btn = QPushButton("关闭")
        refresh_btn.clicked.connect(self.load_logs)
        close_btn.clicked.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addStretch(1)
        row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.event_text, 2)
        layout.addWidget(self.table, 4)
        layout.addLayout(row)
        self.load_logs()

    def load_logs(self) -> None:
        self.event_text.setPlainText("\n".join(self.logger.read_events()))
        rows = self.logger.read_logs()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, field in enumerate(LOG_FIELDS):
                self.table.setItem(r, c, QTableWidgetItem(str(row.get(field, ""))))
        self.table.resizeColumnsToContents()

