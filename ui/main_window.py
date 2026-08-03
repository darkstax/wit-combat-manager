"""TRPG 战斗管理器 - 主窗口 (PySide6)"""

import json
import os
import sys
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QStatusBar,
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QFileDialog, QSlider,
    QDialog, QApplication, QFrame, QStyle,
)
from qfluentwidgets import (
    ComboBox,
    PushButton,
    RoundMenu,
    SmoothScrollArea,
    TabWidget,
    TextEdit,
    ToolButton,
)
from PySide6.QtCore import QEvent, QPoint, QTimer, Qt, Signal, QObject, QUrl
from PySide6.QtGui import QAction, QPixmap, QPainter, QFont, QDesktopServices
from app_paths import writable_data_dir
from models import RuleMode, Unit
from persistence import load_rosters, load_text, save_rosters, save_text
from ui.unit_panel import UnitPanel
from ui.combat_panel import CombatPanel
from ui.fluent import (
    animate_window_entrance,
    apply_fluent_style,
    enable_mica,
    fade_in,
    info_box,
    install_tab_fade,
    standard_icon,
    warn_box,
)

BASE_DIR = str(writable_data_dir())
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
COMBAT_LOG_PATH = os.path.join(BASE_DIR, "combat_log.txt")
GM_LOG_PATH = os.path.join(BASE_DIR, "gm_log.txt")


def _load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_settings(data: dict):
    save_text(SETTINGS_PATH, json.dumps(data, ensure_ascii=False, indent=2))


class LogSignal(QObject):
    message = Signal(str)


class BackgroundWidget(QWidget):
    """绘制水印背景图的自定义 Widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._scaled_pixmap: QPixmap | None = None
        self._opacity: float = 0.35

    def set_background(self, path: str | None, opacity: float = 0.35):
        if path and os.path.exists(path):
            self._pixmap = QPixmap(path)
            self._opacity = opacity
        else:
            self._pixmap = None
        self._scaled_pixmap = None
        self.update()

    def set_opacity(self, opacity: float):
        self._opacity = opacity
        if self._pixmap:
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap or self._pixmap.isNull():
            return
        if self._scaled_pixmap is None or self._scaled_pixmap.size() != self.size():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self._scaled_pixmap = scaled.copy(
                max(0, (scaled.width() - self.width()) // 2),
                max(0, (scaled.height() - self.height()) // 2),
                self.width(),
                self.height(),
            )
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawPixmap(0, 0, self._scaled_pixmap)
        painter.end()

    def resizeEvent(self, event):
        self._scaled_pixmap = None
        super().resizeEvent(event)


class WatermarkDialog(QDialog):
    """背景水印强度调节"""

    def __init__(self, current: float, parent=None):
        super().__init__(parent)
        self.result = None
        self.setWindowTitle("背景水印强度")
        self.setFixedSize(380, 170)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("背景图显示强度 (0.10=极淡 ~ 0.70=浓):"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(10, 70)
        self.slider.setValue(int(current * 100))
        layout.addWidget(self.slider)

        self.value_label = QLabel(f"当前强度: {current:.2f}")
        self.value_label.setFont(QFont(self.value_label.font().family(), 14, QFont.Bold))
        self.value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.value_label)
        self.slider.valueChanged.connect(lambda v: self.value_label.setText(f"当前强度: {v / 100:.2f}"))

        layout.addWidget(QLabel("（背景图将透过半透明控件显示）"))

        btn_layout = QHBoxLayout()
        save_btn = PushButton("保存")
        cancel_btn = PushButton("取消")
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_save(self):
        self.result = self.slider.value() / 100.0
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._integrated_title_bar = False
        if sys.platform == "win32" and hasattr(Qt, "ExpandedClientAreaHint"):
            self.setWindowFlags(
                self.windowFlags()
                | Qt.ExpandedClientAreaHint
                | Qt.NoTitleBarBackgroundHint
            )
            self._integrated_title_bar = True
        apply_fluent_style(QApplication.instance())
        self.setObjectName("AppSurface")
        self.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
        self.setWindowTitle("WIT 战斗管理器 - Walk In the Terra")
        self.resize(1180, 780)
        self.setMinimumSize(900, 620)

        self.units: list[Unit] = []
        self.settings = _load_settings()
        self.rulebook_dir = str(self.settings.get("rulebook_dir") or "")
        self.rulebook_pdf = str(self.settings.get("rulebook_pdf") or "")
        self._using_preview = False
        if self.rulebook_dir:
            from rule_catalog import refresh_shared_catalog, scan_directory_for_workbooks

            refresh_shared_catalog(scan_directory_for_workbooks(self.rulebook_dir))
        else:
            from rule_catalog import detect_builtin_preview_paths, refresh_shared_catalog

            preview_paths = detect_builtin_preview_paths()
            if preview_paths:
                refresh_shared_catalog(preview_paths)
                self._using_preview = True
        self.rule_mode = RuleMode.coerce(self.settings.get("rule_mode", RuleMode.V1_2))
        self.rosters = {mode.value: [] for mode in RuleMode}
        self._changing_rule_mode = False
        self._loading_logs = False
        self.rule_browser = None
        self._safe_area_connected = False
        self._log_signal = LogSignal()
        self._log_signal.message.connect(self._append_log)

        self._build_ui()
        self._apply_background()
        self._load_data()

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("AppSurface")
        central.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
        self.setCentralWidget(central)
        central.resizeEvent = self._on_central_resize

        self.bg_widget = BackgroundWidget(central)
        self.bg_widget.setGeometry(0, 0, central.width(), central.height())
        self.bg_widget.lower()

        self.content = QWidget(central)
        self.content.setObjectName("AppContent")
        self.content.setAttribute(Qt.WA_ContentsMarginsRespectsSafeArea, False)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        command_bar = QFrame()
        command_bar.setObjectName("IntegratedTitleBar")
        command_bar.setMinimumHeight(48)
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(14, 4, 10, 4)
        command_layout.setSpacing(8)
        self._title_bar_layout = command_layout

        self.rule_mode_combo = ComboBox()
        self.rule_mode_combo.setToolTip("切换 0.3 / 1.2 规则与独立单位名单")
        for mode in RuleMode:
            self.rule_mode_combo.addItem(f"v{mode.value}", userData=mode.value)
        self.rule_mode_combo.setCurrentIndex(
            self.rule_mode_combo.findData(self.rule_mode.value)
        )
        self.rule_mode_combo.currentIndexChanged.connect(self._on_rule_mode_changed)
        command_layout.addWidget(self.rule_mode_combo)
        command_layout.addStretch()

        self.rule_browser_action = QAction("规则查询", self)
        self.rule_browser_action.setShortcut("Ctrl+K")
        self.rule_browser_action.triggered.connect(self._open_rule_browser)
        self.addAction(self.rule_browser_action)

        query_btn = PushButton("规则查询")
        query_btn.setIcon(standard_icon(self, QStyle.SP_FileDialogContentsView))
        query_btn.clicked.connect(self._open_rule_browser)
        command_layout.addWidget(query_btn)

        self.more_menu = RoundMenu(title="", parent=self)
        self.more_menu.addAction(self.rule_browser_action)
        self.more_menu.addSeparator()
        rulebook_dir_action = QAction("规则书路径（Excel）...", self)
        rulebook_dir_action.triggered.connect(self._set_rulebook_dir)
        self.more_menu.addAction(rulebook_dir_action)
        rulebook_pdf_action = QAction("打开规则书（PDF）...", self)
        rulebook_pdf_action.triggered.connect(self._open_rulebook_pdf)
        self.more_menu.addAction(rulebook_pdf_action)
        self.more_menu.addSeparator()
        bg_action = QAction("设置背景图片...", self)
        bg_action.triggered.connect(self._set_background)
        self.more_menu.addAction(bg_action)
        opacity_action = QAction("背景水印强度...", self)
        opacity_action.triggered.connect(self._set_watermark)
        self.more_menu.addAction(opacity_action)
        clear_action = QAction("清除背景图片", self)
        clear_action.triggered.connect(self._clear_background)
        self.more_menu.addAction(clear_action)
        self.more_menu.addSeparator()
        export_action = QAction("导出战斗日志...", self)
        export_action.triggered.connect(self._export_log)
        self.more_menu.addAction(export_action)
        self.more_btn = ToolButton()
        self.more_btn.setText("更多")
        self.more_btn.setIcon(standard_icon(self, QStyle.SP_ArrowDown))
        self.more_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.more_btn.setAccessibleName("更多菜单")
        self.more_btn.clicked.connect(self._show_more_menu)
        command_layout.addWidget(self.more_btn)
        layout.addWidget(command_bar)

        body = QWidget()
        body.setObjectName("MainBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 0, 12, 10)
        body_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        self.unit_panel = UnitPanel()
        self.unit_panel.set_rule_mode(self.rule_mode)
        self.unit_panel.units_changed.connect(self._on_units_changed)
        splitter.addWidget(self.unit_panel)

        workspace = QWidget()
        workspace.setObjectName("Workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(10, 10, 10, 10)
        workspace_layout.setSpacing(8)

        work_splitter = QSplitter(Qt.Vertical)
        work_splitter.setObjectName("WorkSplitter")
        work_splitter.setHandleWidth(14)
        self.combat_panel = CombatPanel()
        self.combat_panel.set_rule_mode(self.rule_mode)
        self.combat_panel.set_unit_provider(self.unit_panel)
        self.unit_panel.selection_changed.connect(self.combat_panel.set_selected_target)
        self.combat_panel.setMinimumHeight(240)
        combat_scroll = SmoothScrollArea()
        combat_scroll.setWidgetResizable(True)
        combat_scroll.setFrameShape(QFrame.NoFrame)
        combat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        combat_scroll.setWidget(self.combat_panel)
        work_splitter.addWidget(combat_scroll)
        self.combat_panel.attach_splitter(work_splitter)

        self.combat_panel.set_log_callback(self.append_log)

        log_tabs = TabWidget()
        self.log_text = TextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("战斗记录会显示在这里")
        self.gm_log_text = TextEdit()
        self.gm_log_text.setPlaceholderText("GM 备注")
        self.gm_log_text.textChanged.connect(self._persist_logs)
        self.combat_panel.order_heading.setVisible(False)
        log_tabs.addTab(self.combat_panel.order_list, "行动顺序")
        log_tabs.addTab(self.log_text, "战斗日志")
        log_tabs.addTab(self.gm_log_text, "GM 日志")
        install_tab_fade(log_tabs)
        # 防止展开“修正”时被 QSplitter 完全挤没，保证至少能看到几行日志
        log_tabs.setMinimumHeight(120)
        work_splitter.addWidget(log_tabs)
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 2)
        work_splitter.setSizes([300, 280])
        work_splitter.setChildrenCollapsible(False)
        workspace_layout.addWidget(work_splitter)

        splitter.addWidget(workspace)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 800])
        splitter.setChildrenCollapsible(False)
        body_layout.addWidget(splitter, 1)
        layout.addWidget(body, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

        self._enable_transparent_widgets()


    def _enable_transparent_widgets(self):
        """Keep viewport-backed widgets compatible with the translucent theme."""
        self.content.setAttribute(Qt.WA_StyledBackground, True)

        from PySide6.QtWidgets import QTextEdit, QListWidget, QTreeWidget

        def _apply(widget: QWidget):
            if isinstance(widget, (QTextEdit, QListWidget, QTreeWidget)):
                vp = widget.viewport()
                if vp:
                    vp.setAutoFillBackground(False)
            for child in widget.children():
                if isinstance(child, QWidget):
                    _apply(child)

        _apply(self.content)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_entrance_animated", False):
            self._entrance_animated = True
            animate_window_entrance(self)
        try:
            enable_mica(self)
        except Exception:
            pass
        handle = self.windowHandle()
        if handle is None:
            return
        if not self._safe_area_connected and hasattr(handle, "safeAreaMarginsChanged"):
            handle.safeAreaMarginsChanged.connect(self._schedule_title_bar_metrics)
            handle.screenChanged.connect(self._schedule_title_bar_metrics)
            self._safe_area_connected = True
        self._schedule_title_bar_metrics()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._schedule_title_bar_metrics()

    def _schedule_title_bar_metrics(self, *_args):
        QTimer.singleShot(0, self._apply_title_safe_area)

    def _apply_title_safe_area(self):
        if not hasattr(self, "_title_bar_layout"):
            return
        handle = self.windowHandle()
        margins = handle.safeAreaMargins() if handle is not None else None
        safe_left = max(0, margins.left()) if margins is not None else 0
        safe_right = max(0, margins.right()) if margins is not None else 0
        safe_top = max(0, margins.top()) if margins is not None else 0

        # Qt reports the top title-bar inset on Windows, but not the native
        # caption-button width. Derive it from the system caption height so the
        # command buttons stay clear across DPI and display changes.
        caption_width = 0
        native_title_width = 0
        if self._integrated_title_bar:
            caption_width = int(safe_top * 5.4 + 0.999) + 12 if safe_top else 150
            native_title_width = 300
        self._title_bar_layout.setContentsMargins(
            14 + max(safe_left, native_title_width),
            4,
            10 + max(safe_right, caption_width),
            4,
        )

    def _show_more_menu(self):
        position = self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height() + 4))
        self.more_menu.popup(position)

    def _open_rule_browser(self):
        if self.rule_browser is None:
            from rule_catalog import detect_builtin_preview_paths, scan_directory_for_workbooks
            from ui.rule_browser import RuleBrowserDialog

            if self.rulebook_dir:
                workbook_paths = scan_directory_for_workbooks(self.rulebook_dir)
                is_preview = False
            else:
                workbook_paths = detect_builtin_preview_paths()
                is_preview = bool(workbook_paths)
            self.rule_browser = RuleBrowserDialog(
                self,
                initial_version=self.rule_mode,
                workbook_paths=workbook_paths,
                is_preview=is_preview,
            )
        self.rule_browser.open_for_version(self.rule_mode)

    # ============================================================
    # 规则书
    # ============================================================

    def _set_rulebook_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "选择规则书 Excel 工作簿目录", self.rulebook_dir or ""
        )
        if not directory:
            return
        from rule_catalog import WORKBOOK_FILENAMES, refresh_shared_catalog, scan_directory_for_workbooks

        paths = scan_directory_for_workbooks(directory)
        refresh_shared_catalog(paths)
        self.rulebook_dir = directory
        self.settings["rulebook_dir"] = directory
        _save_settings(self.settings)
        if len(paths) == len(WORKBOOK_FILENAMES):
            info_box(
                self, "规则书路径", f"已载入全部 {len(paths)} 份规则书工作簿：\n{directory}"
            )
        else:
            missing = [
                filename
                for filename in WORKBOOK_FILENAMES.values()
                if not any(
                    path.name.casefold() == filename.casefold()
                    for path in paths.values()
                )
            ]
            warn_box(
                self, "规则书路径",
                "目录中未找到规则书工作簿，请在目录中放置以下文件：\n\n"
                + "\n".join(missing),
            )

    def _open_rulebook_pdf(self):
        if not (self.rulebook_pdf and os.path.exists(self.rulebook_pdf)):
            path, _ = QFileDialog.getOpenFileName(
                self, "选择规则书（PDF）", "",
                "PDF 文件 (*.pdf);;所有文件 (*.*)"
            )
            if not path:
                return
            self.rulebook_pdf = path
            self.settings["rulebook_pdf"] = path
            _save_settings(self.settings)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.rulebook_pdf))

    def _on_central_resize(self, event):
        """central 大小变化时，同步背景层和内容层"""
        w = self.centralWidget().width()
        h = self.centralWidget().height()
        self.bg_widget.setGeometry(0, 0, w, h)
        self.content.setGeometry(0, 0, w, h)

    # ============================================================
    # 背景
    # ============================================================

    def _set_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)"
        )
        if not path:
            return
        self.settings["bg_image"] = path
        _save_settings(self.settings)
        self._apply_background()

    def _clear_background(self):
        self.settings.pop("bg_image", None)
        _save_settings(self.settings)
        self.bg_widget.set_background(None)

    def _set_watermark(self):
        current = self.settings.get("bg_opacity", 0.35)
        dlg = WatermarkDialog(current, self)
        if dlg.exec() == QDialog.Accepted and dlg.result is not None:
            self.settings["bg_opacity"] = dlg.result
            _save_settings(self.settings)
            self.bg_widget.set_opacity(dlg.result)

    def _apply_background(self):
        path = self.settings.get("bg_image", "")
        opacity = self.settings.get("bg_opacity", 0.35)
        self.bg_widget.set_background(path or None, opacity)

    # ============================================================
    # 数据
    # ============================================================

    def _load_data(self):
        store = load_rosters(default_rule_mode=self.rule_mode)
        self.rosters = store.rosters
        self.rule_mode = RuleMode.coerce(store.active_rule_mode)
        self._changing_rule_mode = True
        self.rule_mode_combo.setCurrentIndex(
            self.rule_mode_combo.findData(self.rule_mode.value)
        )
        self._changing_rule_mode = False
        self.units = self.rosters[self.rule_mode.value]
        self.unit_panel.set_rule_mode(self.rule_mode)
        self.combat_panel.set_rule_mode(self.rule_mode)
        self.unit_panel.load_units(self.units)
        self._load_logs()
        self._update_status()

    def _on_units_changed(self, units: list[Unit]):
        self.units = units
        saved = self._save()
        self.unit_panel.last_persist_ok = saved
        if saved:
            self._update_status()

    def _save(self) -> bool:
        try:
            self.rosters[self.rule_mode.value] = self.units
            path = save_rosters(self.rosters, self.rule_mode)
            self.status_label.setText(f"已保存到 {path}")
            return True
        except OSError as exc:
            self.status_label.setText(f"保存失败: {exc}")
            return False

    def _update_status(self):
        p_count = sum(1 for u in self.units if u.unit_type in ("player", "ally"))
        m_count = sum(1 for u in self.units if u.unit_type == "monster")
        a_count = sum(1 for u in self.units if u.unit_type == "ally")
        self.status_label.setText(
            f"规则 v{self.rule_mode.value} | 玩家队: {p_count} | "
            f"友方: {a_count} | 怪物: {m_count} | 共 {len(self.units)} 单位"
        )

    def _on_rule_mode_changed(self):
        if self._changing_rule_mode:
            return
        requested = RuleMode.coerce(self.rule_mode_combo.currentData())
        if requested == self.rule_mode:
            return
        if self.combat_panel.combat_state and self.combat_panel.combat_state.active:
            info_box(self, "战斗进行中", "请先结束当前战斗，再切换规则版本。")
            self._changing_rule_mode = True
            self.rule_mode_combo.setCurrentIndex(
                self.rule_mode_combo.findData(self.rule_mode.value)
            )
            self._changing_rule_mode = False
            return

        self.rosters[self.rule_mode.value] = self.units
        self.rule_mode = requested
        self.units = self.rosters.setdefault(requested.value, [])
        self.unit_panel.set_rule_mode(requested)
        self.unit_panel.load_units(self.units)
        self.combat_panel.set_rule_mode(requested)
        self.combat_panel.set_selected_target(None)
        if self.rule_browser is not None:
            self.rule_browser.set_version(requested)
        self.settings["rule_mode"] = requested.value
        try:
            _save_settings(self.settings)
        except OSError as exc:
            self.status_label.setText(f"设置保存失败: {exc}")
        self._save()
        self._update_status()
        fade_in(self.unit_panel, duration=170, start_opacity=0.82)
        fade_in(self.combat_panel, duration=170, start_opacity=0.82)

    def closeEvent(self, event):
        try:
            self._save()
        except Exception:
            pass
        try:
            self._save_logs()
        except Exception:
            pass
        super().closeEvent(event)

    # ============================================================
    # 日志
    # ============================================================

    def append_log(self, message: str):
        self._log_signal.message.emit(message)

    def _append_log(self, message: str):
        self.log_text.append(message)
        self._persist_logs()

    def _persist_logs(self):
        if self._loading_logs:
            return
        try:
            self._save_logs()
        except OSError as exc:
            self.status_label.setText(f"日志保存失败: {exc}")

    def _save_logs(self):
        save_text(COMBAT_LOG_PATH, self.log_text.toPlainText())
        save_text(GM_LOG_PATH, self.gm_log_text.toPlainText())

    def _load_logs(self):
        self._loading_logs = True
        try:
            self.log_text.setPlainText(load_text(COMBAT_LOG_PATH))
            self.gm_log_text.setPlainText(load_text(GM_LOG_PATH))
        finally:
            self._loading_logs = False

    def _export_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出战斗日志", "combat_log.txt", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("=== 战斗日志 ===\n")
            f.write(self.log_text.toPlainText())
            f.write("\n\n=== GM日志 ===\n")
            f.write(self.gm_log_text.toPlainText())
        self.status_label.setText(f"日志已导出到 {path}")
