from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from modules.config_manager import ConfigManager
from modules.camera import FileCamera
from modules.camera_thread import CameraThread
from modules.image_loader import list_image_files, read_image
from modules.inspection_service import InspectionService
from modules.models import BagInspectionResult, PairRecord
from .config_window import ConfigWindow
from .log_window import LogWindow
from .ng_browser import NGBrowser
from .qt_utils import set_image
from .roi_dialog import ROIDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.service = InspectionService(self.config_manager)
        self.pairs: List[PairRecord] = []
        self.last_result: Optional[BagInspectionResult] = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_once)
        self.camera_threads: List[CameraThread] = []
        self.realtime_pending: Dict[int, Dict[str, dict]] = {}
        self.realtime_max_pending = 30

        self.setWindowTitle("封口质量检测系统")
        self.resize(1440, 900)
        self._build_ui()
        self._load_default_paths()
        self._apply_style()
        self.append_log("系统启动，等待选择图像文件夹")

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(150)
        for name in ["实时检测", "红外相机", "2D相机", "系统设置", "NG记录", "日志"]:
            item = QListWidgetItem(name)
            item.setTextAlignment(Qt.AlignCenter)
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self.switch_page)

        self.stack = QStackedWidget()
        self.page_runtime = self._build_runtime_page()
        self.page_ir = self._build_camera_page("IR")
        self.page_2d = self._build_camera_page("2D")
        self.page_settings = self._build_settings_page()
        self.page_ng = self._build_ng_page()
        self.page_logs = self._build_logs_page()
        for page in [self.page_runtime, self.page_ir, self.page_2d, self.page_settings, self.page_ng, self.page_logs]:
            self.stack.addWidget(page)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)
        self.sidebar.setCurrentRow(0)

    def _build_runtime_page(self) -> QWidget:
        page = QWidget()

        self.folder_2d = QLineEdit()
        self.folder_ir = QLineEdit()
        btn_2d = QPushButton("选择 2D 文件夹")
        btn_ir = QPushButton("选择红外文件夹")
        btn_pair = QPushButton("图像配对")
        btn_detect = QPushButton("单次检测")
        btn_start = QPushButton("启动")
        btn_stop = QPushButton("停止")
        btn_clear = QPushButton("清零")
        btn_2d.clicked.connect(lambda: self.choose_folder(self.folder_2d))
        btn_ir.clicked.connect(lambda: self.choose_folder(self.folder_ir))
        btn_pair.clicked.connect(self.pair_images)
        btn_detect.clicked.connect(self.inspect_all)
        btn_start.clicked.connect(self.start_runtime)
        btn_stop.clicked.connect(self.stop_runtime)
        btn_clear.clicked.connect(self.clear_runtime)
        btn_start.setObjectName("startButton")
        btn_stop.setObjectName("dangerButton")
        btn_clear.setObjectName("dangerButton")

        path_grid = QGridLayout()
        path_grid.addWidget(QLabel("2D文件夹"), 0, 0)
        path_grid.addWidget(self.folder_2d, 0, 1)
        path_grid.addWidget(btn_2d, 0, 2)
        path_grid.addWidget(QLabel("红外文件夹"), 1, 0)
        path_grid.addWidget(self.folder_ir, 1, 1)
        path_grid.addWidget(btn_ir, 1, 2)
        path_grid.addWidget(btn_pair, 0, 3)
        path_grid.addWidget(btn_detect, 1, 3)

        self.image_ir = QLabel("红外图像")
        self.image_2d = QLabel("2D图像")
        for label in (self.image_ir, self.image_2d):
            label.setMinimumSize(540, 300)
            label.setAlignment(Qt.AlignCenter)
            label.setObjectName("imageView")

        control_row = QHBoxLayout()
        control_row.addWidget(btn_start)
        control_row.addWidget(btn_stop)
        control_row.addWidget(btn_clear)
        control_row.addStretch(1)

        left = QVBoxLayout()
        left.addLayout(path_grid)
        left.addWidget(self.image_ir, 1)
        left.addWidget(self.image_2d, 1)
        left.addLayout(control_row)

        self.ok_count = QLabel("OK: 0")
        self.ng_count = QLabel("NG: 0")
        self.pass_rate = QLabel("合格率: 0.00%")
        self.final_banner = QLabel("结果 -")
        self.result_2d = QLabel("2D：-")
        self.result_ir = QLabel("IR：-")
        self.status_label = QLabel("状态：待机")
        self.io_label = QLabel("IO：-")
        self.ok_count.setObjectName("okText")
        self.ng_count.setObjectName("ngText")
        self.pass_rate.setObjectName("rateText")
        self.final_banner.setObjectName("finalBanner")

        stat_row = QHBoxLayout()
        stat_row.addWidget(self.ok_count)
        stat_row.addWidget(self.ng_count)
        stat_row.addWidget(self.pass_rate)
        stat_row.addStretch(1)

        self.feature_table = QTableWidget(0, 3)
        self.feature_table.setHorizontalHeaderLabels(["来源", "特征", "值"])
        self.pair_table = QTableWidget(0, 6)
        self.pair_table.setHorizontalHeaderLabels(["袋号", "2D图像", "IR图像", "时间差ms", "状态", "综合"])
        self.pair_table.cellDoubleClicked.connect(self.inspect_selected_pair)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("runtimeLog")

        right = QVBoxLayout()
        right.addLayout(stat_row)
        right.addWidget(self.final_banner)
        right.addWidget(self.result_2d)
        right.addWidget(self.result_ir)
        right.addWidget(self.status_label)
        right.addWidget(self.io_label)
        right.addWidget(self._section_label("检测特征"))
        right.addWidget(self.feature_table, 2)
        right.addWidget(self._section_label("图像配对记录"))
        right.addWidget(self.pair_table, 2)
        right.addWidget(self._section_label("运行日志"))
        right.addWidget(self.log_text, 2)

        main = QHBoxLayout(page)
        main.setContentsMargins(14, 14, 14, 14)
        main.addLayout(left, 3)
        main.addLayout(right, 3)
        return page

    def _build_camera_page(self, source: str) -> QWidget:
        page = QWidget()
        image = QLabel(f"{source}相机画面")
        image.setMinimumSize(560, 620)
        image.setAlignment(Qt.AlignCenter)
        image.setObjectName("imageView")
        if source == "IR":
            self.ir_preview = image
            cfg = self.config_manager.config["ir"]
            rows = [
                ("ROI", "当前区域", str(cfg.get("roi", [0, 0, 0, 0]))),
                ("分割方式", "模式", str(cfg.get("segmentation_mode", "pseudocolor"))),
                ("伪彩色分割", "HSV范围", str(cfg.get("pseudocolor_hsv_ranges", []))),
                ("温度检测", "均值范围", f"{cfg['temp_min']} - {cfg['temp_max']} °C"),
                ("尺寸检测", "宽度范围", f"{cfg['min_width']} - {cfg['max_width']} px"),
                ("尺寸检测", "高度范围", f"{cfg['min_height']} - {cfg['max_height']} px"),
                ("面积检测", "面积范围", f"{cfg['min_area']} - {cfg['max_area']}"),
                ("倾斜检测", "最大角度", f"{cfg['max_angle']}°"),
                ("边界检测", "最大粗糙度", str(cfg["max_boundary_roughness"])),
                ("温度均匀性", "最大标准差", f"{cfg['max_temp_std']} °C"),
            ]
        else:
            self.visible_preview = image
            cfg = self.config_manager.config["visible"]
            rows = [
                ("ROI", "当前区域", str(cfg.get("roi", [0, 0, 0, 0]))),
                ("银边检测", "亮度阈值", str(cfg["silver_v_threshold"])),
                ("银边检测", "饱和度阈值", str(cfg["silver_s_threshold"])),
                ("银边检测", "最大面积", str(cfg["max_silver_area"])),
                ("银边检测", "最大占比", str(cfg["max_silver_ratio"])),
                ("异物检测", "最大面积", str(cfg["max_foreign_area"])),
                ("异物检测", "最小连通域", str(cfg["min_defect_area"])),
                ("ROI尺寸", "宽高范围", f"{cfg['min_width']}-{cfg['max_width']} / {cfg['min_height']}-{cfg['max_height']}"),
            ]

        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["启用", "检测项", "参数", "阈值"])
        for r, (group, key, value) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem("■"))
            table.setItem(r, 1, QTableWidgetItem(group))
            table.setItem(r, 2, QTableWidgetItem(key))
            table.setItem(r, 3, QTableWidgetItem(value))
        table.resizeColumnsToContents()

        btn_roi = QPushButton("ROI设置")
        btn_refresh = QPushButton("刷新参数")
        btn_config = QPushButton("编辑配置")
        btn_roi.clicked.connect(lambda checked=False, s=source: self.open_roi_dialog(s))
        btn_refresh.clicked.connect(self.refresh_camera_pages)
        btn_config.clicked.connect(self.open_config)

        buttons = QHBoxLayout()
        buttons.addWidget(btn_roi)
        buttons.addWidget(btn_refresh)
        buttons.addWidget(btn_config)
        buttons.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(self._section_label("检测项设置"))
        right.addWidget(table)
        right.addLayout(buttons)
        right.addStretch(1)

        layout = QHBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(image, 3)
        layout.addLayout(right, 4)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        self.settings_editor = QTextEdit()
        self.settings_editor.setPlainText(self.config_manager.to_json_text())
        self.settings_editor.setObjectName("configEditor")
        save_btn = QPushButton("保存设置")
        reload_btn = QPushButton("重新加载")
        open_btn = QPushButton("打开独立配置窗口")
        save_btn.clicked.connect(self.save_settings_text)
        reload_btn.clicked.connect(lambda: self.settings_editor.setPlainText(self.config_manager.to_json_text()))
        open_btn.clicked.connect(self.open_config)
        save_btn.setObjectName("primaryButton")

        buttons = QHBoxLayout()
        buttons.addWidget(save_btn)
        buttons.addWidget(reload_btn)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(self._section_label("系统参数配置"))
        layout.addWidget(self.settings_editor, 1)
        layout.addLayout(buttons)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        self.setting_fields: Dict[tuple[str, str], QLineEdit] = {}
        self.settings_editor = QTextEdit()
        self.settings_editor.setPlainText(self.config_manager.to_json_text())
        self.settings_editor.setVisible(False)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        content_layout.addWidget(self._settings_group("2D 可见光检测参数", [
            ("ROI 模式", "visible", "roi_mode"),
            ("ROI [x,y,w,h]", "visible", "roi"),
            ("按尺寸备用 ROI", "visible", "roi_by_size"),
            ("启用包装袋主体定位", "visible", "package_body_roi_enabled"),
            ("主体内封口搜索范围", "visible", "seal_search_in_body_by_size"),
            ("自动 ROI 搜索范围", "visible", "auto_roi_search_by_size"),
            ("自动 ROI 横向范围", "visible", "auto_roi_x_by_size"),
            ("自动 ROI 高度比例", "visible", "auto_roi_height_ratio"),
            ("自动 ROI 最大宽度", "visible", "auto_roi_max_width_by_size"),
            ("主体分割饱和度阈值", "visible", "package_body_min_saturation"),
            ("主体分割亮度阈值", "visible", "package_body_min_value"),
            ("银边亮度阈值 V", "visible", "silver_v_threshold"),
            ("银边饱和度阈值 S", "visible", "silver_s_threshold"),
            ("最大银边面积", "visible", "max_silver_area"),
            ("最大银边占比", "visible", "max_silver_ratio"),
            ("扩展特征：异物面积阈值", "visible", "max_foreign_area"),
            ("扩展特征：最小连通域", "visible", "min_defect_area"),
        ]))
        content_layout.addWidget(self._settings_group("红外检测参数", [
            ("ROI [x,y,w,h]", "ir", "roi"),
            ("分割模式", "ir", "segmentation_mode"),
            ("伪彩色 HSV 范围", "ir", "pseudocolor_hsv_ranges"),
            ("最小宽度", "ir", "min_width"),
            ("最大宽度", "ir", "max_width"),
            ("最小高度", "ir", "min_height"),
            ("最大高度", "ir", "max_height"),
            ("最小面积", "ir", "min_area"),
            ("最大面积", "ir", "max_area"),
            ("最大倾斜角", "ir", "max_angle"),
            ("最大边界粗糙度", "ir", "max_boundary_roughness"),
            ("最低温度", "ir", "temp_min"),
            ("最高温度", "ir", "temp_max"),
            ("最大温度标准差", "ir", "max_temp_std"),
            ("封口最小长宽比", "ir", "min_seal_aspect_ratio"),
        ]))
        content_layout.addWidget(self._settings_group("图像配对参数", [
            ("最大时间差 ms", "pairing", "max_time_diff_ms"),
            ("2D 文件夹", "pairing", "folder_2d"),
            ("红外文件夹", "pairing", "folder_ir"),
            ("2D 文件名前缀", "pairing", "visible_prefixes"),
            ("红外文件名前缀", "pairing", "ir_prefixes"),
            ("配对文件扩展名", "pairing", "pair_extensions"),
        ]))
        content_layout.addWidget(self._settings_group("保存、运行与 IO 参数", [
            ("NG 图像保存目录", "save", "ng_image_dir"),
            ("标注图保存目录", "save", "annotated_dir"),
            ("日志保存目录", "save", "log_dir"),
            ("日志保留天数", "save", "log_keep_days"),
            ("实时循环间隔 ms", "runtime", "poll_interval_ms"),
            ("模拟 IO", "io", "simulate"),
            ("OK 信号名", "io", "ok_signal"),
            ("NG 信号名", "io", "ng_signal"),
            ("报警信号名", "io", "alarm_signal"),
            ("剔除信号名", "io", "reject_signal"),
        ]))
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        save_btn = QPushButton("保存页面参数")
        reload_btn = QPushButton("重新加载")
        open_btn = QPushButton("高级 JSON 配置")
        save_btn.clicked.connect(self.save_settings_form)
        reload_btn.clicked.connect(self.load_settings_form)
        open_btn.clicked.connect(self.open_config)
        save_btn.setObjectName("primaryButton")

        buttons = QHBoxLayout()
        buttons.addWidget(save_btn)
        buttons.addWidget(reload_btn)
        buttons.addWidget(open_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(self._section_label("系统参数配置"))
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)
        self.load_settings_form()
        return page

    def _settings_group(self, title: str, rows: List[tuple[str, str, str]]) -> QGroupBox:
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for row, (label_text, section, key) in enumerate(rows):
            label = QLabel(label_text)
            field = QLineEdit()
            self.setting_fields[(section, key)] = field
            grid.addWidget(label, row, 0)
            grid.addWidget(field, row, 1)
        return group

    def load_settings_form(self) -> None:
        self.config_manager.load()
        for (section, key), field in self.setting_fields.items():
            value = self.config_manager.config.get(section, {}).get(key, "")
            field.setText(self._format_setting_value(value))
        self.settings_editor.setPlainText(self.config_manager.to_json_text())
        self.append_log("系统设置页面已重新加载")

    def save_settings_form(self) -> None:
        try:
            cfg = self.config_manager.config
            for (section, key), field in self.setting_fields.items():
                old_value = cfg.get(section, {}).get(key, "")
                cfg.setdefault(section, {})[key] = self._parse_setting_value(field.text(), old_value)
            self.config_manager.save()
            self.service.reload_config()
            self.settings_editor.setPlainText(self.config_manager.to_json_text())
            self._load_default_paths()
            self.refresh_camera_pages()
            self.append_log("系统页面参数已保存到本地 config.json")
            QMessageBox.information(self, "保存成功", "系统设置已保存到本地 config.json。")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"页面参数无法保存：\n{exc}")

    @staticmethod
    def _format_setting_value(value) -> str:
        if isinstance(value, list):
            if all(not isinstance(item, list) for item in value):
                return ", ".join(str(item) for item in value)
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _parse_setting_value(text: str, old_value):
        text = text.strip()
        if isinstance(old_value, bool):
            return text.lower() in {"1", "true", "yes", "y", "on", "是", "启用"}
        if isinstance(old_value, int) and not isinstance(old_value, bool):
            return int(float(text))
        if isinstance(old_value, float):
            return float(text)
        if isinstance(old_value, list):
            if old_value and isinstance(old_value[0], list):
                return json.loads(text)
            if old_value and all(isinstance(item, int) for item in old_value):
                return [int(float(item.strip())) for item in text.split(",") if item.strip()]
            if old_value and all(isinstance(item, float) for item in old_value):
                return [float(item.strip()) for item in text.split(",") if item.strip()]
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(old_value, dict):
            return json.loads(text)
        return text

    def _build_ng_page(self) -> QWidget:
        page = QWidget()
        open_btn = QPushButton("打开 NG 图像浏览窗口")
        refresh_btn = QPushButton("刷新 NG 文件列表")
        open_btn.clicked.connect(self.open_ng_browser)
        refresh_btn.clicked.connect(self.load_ng_records)
        self.ng_table = QTableWidget(0, 3)
        self.ng_table.setHorizontalHeaderLabels(["结果文件", "日期", "路径"])
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(self._section_label("NG记录"))
        layout.addWidget(self.ng_table, 1)
        row = QHBoxLayout()
        row.addWidget(open_btn)
        row.addWidget(refresh_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _build_logs_page(self) -> QWidget:
        page = QWidget()
        self.saved_log_text = QTextEdit()
        self.saved_log_text.setReadOnly(True)
        self.saved_log_text.setObjectName("runtimeLog")
        self.csv_log_table = QTableWidget(0, 5)
        self.csv_log_table.setHorizontalHeaderLabels(["时间", "袋号", "2D", "IR", "综合"])
        refresh_btn = QPushButton("刷新日志")
        open_btn = QPushButton("打开完整日志窗口")
        refresh_btn.clicked.connect(self.load_saved_logs)
        open_btn.clicked.connect(self.open_log_window)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(self._section_label("运行日志（本地 txt 保存）"))
        layout.addWidget(self.saved_log_text, 2)
        layout.addWidget(self._section_label("检测记录（本地 CSV 保存）"))
        layout.addWidget(self.csv_log_table, 3)
        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addWidget(open_btn)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _load_default_paths(self) -> None:
        cfg = self.config_manager.config["pairing"]
        self.folder_2d.setText(str(self.config_manager.resolve_path(cfg["folder_2d"])))
        self.folder_ir.setText(str(self.config_manager.resolve_path(cfg["folder_ir"])))

    def choose_folder(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图像文件夹", target.text())
        if folder:
            target.setText(folder)
            self.append_log(f"选择图像文件夹：{folder}")

    def pair_images(self) -> None:
        self.service.reload_config()
        self.pairs = self.service.pair_folders(self.folder_2d.text(), self.folder_ir.text())
        self.pair_table.setRowCount(len(self.pairs))
        for row, pair in enumerate(self.pairs):
            values = [
                pair.bag_id,
                pair.image_2d_path.name if pair.image_2d_path else "",
                pair.image_ir_path.name if pair.image_ir_path else "",
                "" if pair.time_diff_ms is None else f"{pair.time_diff_ms:.1f}",
                pair.status,
                "",
            ]
            for col, value in enumerate(values):
                self.pair_table.setItem(row, col, QTableWidgetItem(value))
        self.pair_table.resizeColumnsToContents()
        self.append_log(f"完成图像配对：{len(self.pairs)} 条记录")

    def inspect_all(self) -> None:
        if not self.pairs:
            self.pair_images()
        for row, pair in enumerate(self.pairs):
            result = self.service.inspect_pair(pair)
            self.show_result(result)
            self.pair_table.setItem(row, 5, QTableWidgetItem(result.final_result))
        self.update_status()
        self.load_saved_logs()

    def inspect_selected_pair(self, row: int, _col: int) -> None:
        if 0 <= row < len(self.pairs):
            result = self.service.inspect_pair(self.pairs[row])
            self.show_result(result)
            self.pair_table.setItem(row, 5, QTableWidgetItem(result.final_result))
            self.update_status()

    def start_runtime(self) -> None:
        if self.camera_threads:
            self.append_log("实时相机线程已在运行")
            return
        self.service.stats.running = True
        self.realtime_pending.clear()
        interval = int(self.config_manager.config["runtime"].get("poll_interval_ms", 300))
        try:
            camera_2d = FileCamera(self.folder_2d.text(), camera_id="2D", loop=True, interval_ms=interval, logger=self.service.logger)
            camera_ir = FileCamera(self.folder_ir.text(), camera_id="IR", loop=True, interval_ms=interval, logger=self.service.logger)
            thread_2d = CameraThread(camera_2d, camera_id="2D", timeout_ms=interval, logger=self.service.logger)
            thread_ir = CameraThread(camera_ir, camera_id="IR", timeout_ms=interval, logger=self.service.logger)
            for thread in (thread_2d, thread_ir):
                thread.packet_signal.connect(self.handle_camera_packet)
                thread.status_signal.connect(self.append_log)
                thread.error_signal.connect(self.handle_camera_error)
                thread.start_capture()
                thread.start()
            self.camera_threads = [thread_2d, thread_ir]
            self.status_label.setText("状态：实时运行")
            self.append_log("实时运行已启动：使用 FileCamera + CameraThread 按 frame_id 配对")
        except Exception as exc:
            self.service.stats.running = False
            self.append_log(f"实时运行启动失败：{exc}")
            QMessageBox.critical(self, "启动失败", str(exc))

    def stop_runtime(self) -> None:
        self.timer.stop()
        for thread in self.camera_threads:
            thread.stop()
        for thread in self.camera_threads:
            thread.wait(1500)
        self.camera_threads = []
        self.realtime_pending.clear()
        self.service.stats.running = False
        self.status_label.setText("状态：已停止")
        self.append_log("实时运行已停止")

    def clear_runtime(self) -> None:
        if self.camera_threads:
            self.stop_runtime()
        self.service.stats.total = 0
        self.service.stats.ok = 0
        self.service.stats.ng = 0
        self.service.stats.last_ng_reason = ""
        self.service.io_controller.reset()
        self.feature_table.setRowCount(0)
        self.pair_table.setRowCount(0)
        self.pairs = []
        self.last_result = None
        self.update_status()
        self.final_banner.setText("结果 -")
        self.result_2d.setText("2D：-")
        self.result_ir.setText("IR：-")
        self.io_label.setText("IO：-")
        self.append_log("运行统计已清零")

    def poll_once(self) -> None:
        results = self.service.inspect_new_pairs(self.folder_2d.text(), self.folder_ir.text())
        if not results:
            self.update_status(extra="未发现新配对图像")
            return
        for result in results:
            self.show_result(result)
        self.pair_images()

    def handle_camera_packet(self, packet: dict) -> None:
        camera_id = packet.get("camera_id")
        frame_id = int(packet.get("frame_id") or 0)
        if frame_id <= 0 or camera_id not in ("2D", "IR"):
            return

        bucket = self.realtime_pending.setdefault(frame_id, {})
        bucket[camera_id] = packet
        self._cleanup_realtime_pending(frame_id)
        if len(self.realtime_pending) > self.realtime_max_pending:
            oldest = min(self.realtime_pending.keys())
            if oldest != frame_id:
                self.realtime_pending.pop(oldest, None)
                self.append_log(f"实时缓存过多，丢弃旧 frame_id={oldest}")

        if "2D" in bucket and "IR" in bucket:
            packet_2d = bucket["2D"]
            packet_ir = bucket["IR"]
            self.realtime_pending.pop(frame_id, None)
            max_diff_ms = float(self.config_manager.config["pairing"].get("max_time_diff_ms", 1000))
            ts_2d = float(packet_2d.get("timestamp") or 0)
            ts_ir = float(packet_ir.get("timestamp") or 0)
            time_diff_ms = abs(ts_2d - ts_ir) * 1000.0 if ts_2d and ts_ir else None
            if time_diff_ms is None or time_diff_ms > max_diff_ms:
                self.append_log(
                    f"实时配对异常 frame_id={frame_id}: "
                    f"时间差={time_diff_ms if time_diff_ms is not None else 'N/A'} ms，阈值={max_diff_ms} ms，已丢弃"
                )
                return
            try:
                result = self.service.inspect_packets(frame_id, packet_2d, packet_ir, save=True)
                self.show_result(result)
                self._append_realtime_pair_row(result)
            except Exception as exc:
                self.append_log(f"实时检测异常 frame_id={frame_id}: {exc}")

    def _cleanup_realtime_pending(self, current_frame_id: int) -> None:
        stale = [
            fid for fid in self.realtime_pending
            if current_frame_id - fid > self.realtime_max_pending // 2
        ]
        for fid in stale:
            missing = {"2D", "IR"} - set(self.realtime_pending.get(fid, {}).keys())
            self.realtime_pending.pop(fid, None)
            self.append_log(f"实时配对超时 frame_id={fid}: 缺失 {','.join(sorted(missing)) or '未知'}，已丢弃")

    def handle_camera_error(self, message: str) -> None:
        self.append_log(message)
        self.status_label.setText("状态：相机异常")

    def _append_realtime_pair_row(self, result: BagInspectionResult) -> None:
        row = self.pair_table.rowCount()
        self.pair_table.insertRow(row)
        pair = result.pair
        values = [
            pair.bag_id,
            pair.image_2d_path.name if pair.image_2d_path else "",
            pair.image_ir_path.name if pair.image_ir_path else "",
            "" if pair.time_diff_ms is None else f"{pair.time_diff_ms:.1f}",
            "FRAME_ID",
            result.final_result,
        ]
        for col, value in enumerate(values):
            self.pair_table.setItem(row, col, QTableWidgetItem(value))
        self.pair_table.scrollToBottom()

    def show_result(self, result: BagInspectionResult) -> None:
        self.last_result = result
        image_2d = result.result_2d.annotated_image if result.result_2d.annotated_image is not None else result.result_2d.raw_image
        image_ir = result.result_ir.annotated_image if result.result_ir.annotated_image is not None else result.result_ir.raw_image
        set_image(self.image_2d, image_2d)
        set_image(self.image_ir, image_ir)
        if hasattr(self, "visible_preview"):
            set_image(self.visible_preview, image_2d)
        if hasattr(self, "ir_preview"):
            set_image(self.ir_preview, image_ir)
        self.result_2d.setText(f"2D：{result.result_2d.result}")
        self.result_ir.setText(f"IR：{result.result_ir.result}")
        self.final_banner.setText(f"结果 {result.final_result}")
        self.final_banner.setProperty("state", result.final_result)
        self.final_banner.style().unpolish(self.final_banner)
        self.final_banner.style().polish(self.final_banner)
        self.io_label.setText(self._format_io(result.io_state))
        self.populate_features(result)
        reason = "; ".join(result.ng_reasons) if result.ng_reasons else "OK"
        self.append_log(f"{result.pair.bag_id} 检测完成：{result.final_result}，原因：{reason}")
        self.update_status()

    def populate_features(self, result: BagInspectionResult) -> None:
        rows = []
        for source, features in [("2D", result.result_2d.features), ("IR", result.result_ir.features)]:
            for key, value in features.items():
                rows.append((source, key, value))
        self.feature_table.setRowCount(len(rows))
        for row, (source, key, value) in enumerate(rows):
            self.feature_table.setItem(row, 0, QTableWidgetItem(str(source)))
            self.feature_table.setItem(row, 1, QTableWidgetItem(str(key)))
            self.feature_table.setItem(row, 2, QTableWidgetItem(str(value)))
        self.feature_table.resizeColumnsToContents()

    def update_status(self, extra: str = "") -> None:
        stats = self.service.stats.to_dict()
        self.ok_count.setText(f"OK: {stats['ok']}")
        self.ng_count.setText(f"NG: {stats['ng']}")
        pass_ratio = 0.0 if stats["total"] == 0 else stats["ok"] / stats["total"]
        self.pass_rate.setText(f"合格率: {pass_ratio:.2%}")
        state = "实时运行" if stats["running"] else "待机"
        text = f"状态：{state} | 总数 {stats['total']} | 最新 {stats['latest_bag_id'] or '-'}"
        if extra:
            text += f" | {extra}"
        self.status_label.setText(text)

    def append_log(self, text: str) -> None:
        self.log_text.append(text)
        self.service.logger.append_event(text)
        if hasattr(self, "saved_log_text"):
            self.saved_log_text.append(text)

    def save_settings_text(self) -> None:
        try:
            self.config_manager.update_from_json_text(self.settings_editor.toPlainText())
            self.service.reload_config()
            self._load_default_paths()
            self.refresh_camera_pages()
            self.append_log("系统参数已保存")
            QMessageBox.information(self, "保存成功", "配置已保存到本地 config.json。")
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", f"JSON 配置无法保存：\n{exc}")

    def refresh_camera_pages(self) -> None:
        self.config_manager.load()
        current = self.stack.currentIndex()
        self.stack.removeWidget(self.page_ir)
        self.stack.removeWidget(self.page_2d)
        self.page_ir.deleteLater()
        self.page_2d.deleteLater()
        self.page_ir = self._build_camera_page("IR")
        self.page_2d = self._build_camera_page("2D")
        self.stack.insertWidget(1, self.page_ir)
        self.stack.insertWidget(2, self.page_2d)
        self.stack.setCurrentIndex(current)
        self.append_log("相机参数页已刷新")

    def load_ng_records(self) -> None:
        records = self.service.logger.list_ng_json()
        self.ng_table.setRowCount(len(records))
        for row, path in enumerate(records):
            self.ng_table.setItem(row, 0, QTableWidgetItem(path.name))
            self.ng_table.setItem(row, 1, QTableWidgetItem(path.parent.name))
            self.ng_table.setItem(row, 2, QTableWidgetItem(str(path)))
        self.ng_table.resizeColumnsToContents()
        self.append_log(f"刷新 NG 记录：{len(records)} 条")

    def load_saved_logs(self) -> None:
        events = self.service.logger.read_events()
        self.saved_log_text.setPlainText("\n".join(events))
        rows = self.service.logger.read_logs()
        self.csv_log_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [row.get("time", ""), row.get("bag_id", ""), row.get("result_2d", ""), row.get("result_ir", ""), row.get("final_result", "")]
            for c, value in enumerate(values):
                self.csv_log_table.setItem(r, c, QTableWidgetItem(value))
        self.csv_log_table.resizeColumnsToContents()

    def switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 4:
            self.load_ng_records()
        elif index == 5:
            self.load_saved_logs()

    def open_config(self) -> None:
        dialog = ConfigWindow(self.config_manager, self)
        dialog.exec_()
        self.service.reload_config()
        self.settings_editor.setPlainText(self.config_manager.to_json_text())
        if hasattr(self, "setting_fields"):
            self.load_settings_form()
        self._load_default_paths()
        self.refresh_camera_pages()

    def open_ng_browser(self) -> None:
        NGBrowser(self.service.logger, self).exec_()

    def open_log_window(self) -> None:
        LogWindow(self.service.logger, self).exec_()

    def open_roi_dialog(self, source: str) -> None:
        image = self._roi_source_image(source)
        if image is None:
            QMessageBox.warning(self, "无法设置ROI", f"没有可用于设置 {source} ROI 的图像，请先选择文件夹或运行一次检测。")
            return

        section = "ir" if source == "IR" else "visible"
        current_roi = self.config_manager.config[section].get("roi", [0, 0, 0, 0])
        dialog = ROIDialog(image, current_roi, f"{source} ROI设置", self)
        if dialog.exec_() != dialog.Accepted:
            return

        roi = list(dialog.roi())
        self.config_manager.config[section]["roi"] = roi
        self.config_manager.save()
        self.service.reload_config()
        if hasattr(self, "settings_editor"):
            self.settings_editor.setPlainText(self.config_manager.to_json_text())
        if hasattr(self, "setting_fields"):
            self.load_settings_form()
        self.refresh_camera_pages()
        self.append_log(f"{source} ROI 已保存：{roi}，后续检测标注图会绘制该 ROI")

    def _roi_source_image(self, source: str):
        if self.last_result is not None:
            if source == "IR" and self.last_result.result_ir.raw_image is not None:
                return self.last_result.result_ir.raw_image
            if source == "2D" and self.last_result.result_2d.raw_image is not None:
                return self.last_result.result_2d.raw_image

        folder = self.folder_ir.text() if source == "IR" else self.folder_2d.text()
        files = list_image_files(folder)
        if not files:
            return None
        return read_image(files[0])

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _format_io(io_state: Dict[str, object]) -> str:
        if not io_state:
            return "IO：-"
        return (
            f"IO：OK={io_state.get('ok_signal', False)} | "
            f"NG={io_state.get('ng_signal', False)} | "
            f"报警={io_state.get('alarm_on', False)} | "
            f"剔除={io_state.get('reject_triggered', False)}"
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #2f343a;
                color: #dce4ec;
                font-family: Microsoft YaHei, SimSun, Arial;
                font-size: 13px;
            }
            QListWidget {
                background: #252a30;
                border: 0;
                outline: 0;
            }
            QListWidget::item {
                height: 52px;
                color: #dce4ec;
                border-left: 4px solid transparent;
            }
            QListWidget::item:selected {
                background: #3f98d7;
                color: white;
                border-left: 4px solid #a9dcff;
            }
            QLabel#imageView {
                background: #1f2429;
                border: 1px solid #5a626b;
                color: #8f9ca8;
            }
            QLabel#sectionLabel {
                color: #5dd6e6;
                font-weight: 700;
                padding-top: 8px;
            }
            QLabel#okText {
                color: #75f070;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#ngText {
                color: #ff6969;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#rateText {
                color: #f0d95b;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#finalBanner {
                border: 1px solid #6b4141;
                color: #dce4ec;
                font-size: 22px;
                font-weight: 700;
                padding: 12px;
                qproperty-alignment: AlignCenter;
            }
            QLabel#finalBanner[state="OK"] {
                color: #74f070;
                border-color: #4aa05d;
            }
            QLabel#finalBanner[state="NG"] {
                color: #ff6969;
                border-color: #a05050;
            }
            QLineEdit, QTextEdit, QTableWidget {
                background: #3a4047;
                border: 1px solid #525b65;
                color: #edf3f8;
                selection-background-color: #3f98d7;
            }
            QTextEdit#runtimeLog {
                font-family: Consolas, Microsoft YaHei;
                color: #d6dde5;
            }
            QTextEdit#configEditor {
                font-family: Consolas, Microsoft YaHei;
                font-size: 12px;
            }
            QHeaderView::section {
                background: #454c55;
                color: #dce4ec;
                border: 1px solid #59616a;
                padding: 4px;
            }
            QPushButton {
                background: #4b5562;
                border: 1px solid #606a76;
                color: #f0f4f8;
                padding: 8px 16px;
                min-width: 76px;
            }
            QPushButton:hover {
                background: #596575;
            }
            QPushButton#startButton, QPushButton#primaryButton {
                background: #6bd05e;
                color: white;
                font-weight: 700;
            }
            QPushButton#dangerButton {
                background: #c95d63;
                color: white;
                font-weight: 700;
            }
            """
        )
