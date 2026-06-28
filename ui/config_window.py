from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QPushButton, QTextEdit, QVBoxLayout

from modules.config_manager import ConfigManager


class ConfigWindow(QDialog):
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("参数配置")
        self.resize(760, 620)

        self.editor = QTextEdit()
        self.editor.setPlainText(self.config_manager.to_json_text())
        self.editor.setStyleSheet("font-family: Consolas, Microsoft YaHei, monospace; font-size: 12px;")

        save_btn = QPushButton("保存配置")
        reload_btn = QPushButton("重新加载")
        close_btn = QPushButton("关闭")
        save_btn.clicked.connect(self.save_config)
        reload_btn.clicked.connect(lambda: self.editor.setPlainText(self.config_manager.to_json_text()))
        close_btn.clicked.connect(self.accept)

        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addLayout(btn_row)

    def save_config(self) -> None:
        try:
            self.config_manager.update_from_json_text(self.editor.toPlainText())
            QMessageBox.information(self, "保存成功", "配置已保存到本地 config.json。")
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", f"JSON 配置无法保存：\n{exc}")

