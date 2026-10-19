"""Main application window (English UI).

The window keeps only the essentials: Input, Models and Output mode. Everything
else lives in the tabbed Settings dialog (menu: Settings → Settings…).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..audio import (
    list_input_devices,
    list_loopback_devices,
    list_output_devices,
    output_capture_available,
)
from ..config import (
    APP_NAME,
    ICON_ICO,
    OVERLAY_DIR,
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
    WHISPER_MODELS,
    Config,
    load_config,
    resolved_models_dir,
    save_config,
)
from ..hotkey import GlobalHotkey, parse_hotkey
from ..i18n import current_language, set_language, tr
from ..models import (
    CUSTOM_REPO,
    DEFAULT_TRANSLATION_KEY,
    ModelInfo,
    custom_translation_info,
    custom_whisper_info,
    find_translation_path,
    missing_keys_for_path,
    path_description,
    translation_model_info,
    whisper_model_info,
)
from ..overlay_server import OverlayServer
from ..pipeline import Pipeline
from ..transcriber import GpuInfo, detect_gpu, resolve_device_compute, resolve_model
from .about_dialog import AboutDialog
from .audio_widgets import InputMonitor, LevelMeter
from .download_dialog import MissingModelsDialog, run_download
from .help_dialog import HowToUseDialog
from .models_dialog import ModelsDialog
from .screen_overlay import ScreenOverlay
from .settings_dialog import SettingsDialog

CREDIT_TEXT = "Made by ClassicCyc · MIT · open source"

SAMPLE_LINES = [
    ("This is how your subtitles look in OBS.", "Так ваши субтитры выглядят в OBS."),
    ("The quick brown fox jumps over the lazy dog.", "Быстрая коричневая лиса прыгает через ленивую собаку."),
    ("Thanks for watching the stream!", "Спасибо за просмотр стрима!"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cyctitles")
        self.setWindowIcon(QIcon(str(ICON_ICO)))
        self.setMinimumWidth(600)

        from ..i18n import init_from_config
        from ..ui.theme import apply_theme

        self.cfg: Config = load_config()
        init_from_config()
        apply_theme(getattr(self.cfg, "theme", "auto"))
        self.pipeline: Pipeline | None = None
        self.hotkey: GlobalHotkey | None = None
        self._loading = True
        self._gpu_detected = False
        self._gpu_cache: GpuInfo | None = None
        self._force_quit = False
        self._tray: QSystemTrayIcon | None = None
        self._state = "idle"
        self._tray_start_action: QAction | None = None
        self._tray_mute_action: QAction | None = None
        self._sample_index = 0
        self._settings: SettingsDialog | None = None
        self._monitor: InputMonitor | None = None
        self._test_button: QPushButton | None = None

        self.overlay = OverlayServer(OVERLAY_DIR, self.cfg.overlay_port)
        self.overlay.set_config(self.cfg.overlay.to_payload())
        self.overlay.start()

        self._screen_overlay = ScreenOverlay(self.cfg.overlay.auto_hide_sec)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_config)

        self._build_menu()
        self._build_ui()
        self._load_config_into_ui()
        self._restore_geometry()
        self._setup_tray()

        if self.cfg.auto_start:
            QTimer.singleShot(0, self._auto_start)

    # -- construction --------------------------------------------------------
    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu(tr("menu_settings"))
        settings_action = QAction(tr("menu_settings_action"), self)
        settings_action.triggered.connect(self.open_settings)
        settings_menu.addAction(settings_action)
        settings_menu.addSeparator()
        open_config = QAction(tr("menu_open_config"), self)
        open_config.triggered.connect(self._open_config_folder)
        settings_menu.addAction(open_config)
        open_models_dir = QAction(tr("menu_open_models"), self)
        open_models_dir.triggered.connect(self._open_models_folder)
        settings_menu.addAction(open_models_dir)

        models_menu = self.menuBar().addMenu(tr("menu_models"))
        manage = QAction(tr("menu_manage_models"), self)
        manage.triggered.connect(self._open_models_dialog)
        models_menu.addAction(manage)

        overlay_menu = self.menuBar().addMenu(tr("menu_overlay"))
        open_prev = QAction(tr("menu_open_preview"), self)
        open_prev.triggered.connect(self.open_preview)
        copy_url = QAction(tr("menu_copy_url"), self)
        copy_url.triggered.connect(self.copy_obs_url)
        overlay_menu.addAction(open_prev)
        overlay_menu.addAction(copy_url)
        overlay_menu.addSeparator()
        obs_help = QAction(tr("menu_obs_help"), self)
        obs_help.triggered.connect(self.show_obs_help)
        overlay_menu.addAction(obs_help)

        help_menu = self.menuBar().addMenu(tr("menu_help"))
        how_to = QAction(tr("menu_howto"), self)
        how_to.triggered.connect(self._show_how_to)
        help_menu.addAction(how_to)
        help_menu.addSeparator()
        about = QAction(tr("menu_about"), self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(10)

        layout.addWidget(self._build_input_group())
        layout.addWidget(self._build_models_group())
        layout.addWidget(self._build_output_group())

        # -- Start -----------------------------------------------------------
        self.start_button = QPushButton(tr("btn_start"))
        self.start_button.setCheckable(True)
        self.start_button.setMinimumHeight(48)
        self.start_button.setStyleSheet(
            "QPushButton{font-size:16px;font-weight:600;}"
            "QPushButton:checked{background:#c0392b;color:white;}"
        )
        self.start_button.toggled.connect(self._on_start_toggled)
        layout.addWidget(self.start_button)

        self.info_label = QLabel(tr("info_ready"))
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.info_label)

        self.hotkey_label = QLabel()
        self.hotkey_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.hotkey_label)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        credit = QLabel(tr("credit"))
        credit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(credit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        self.setCentralWidget(scroll)

        self.state_label = QLabel("● " + tr("state_idle"))
        self.state_label.setStyleSheet("color: #888; font-weight: 600; padding: 0 6px;")
        self.statusBar().addPermanentWidget(self.state_label)
        self.caption_label = QLabel("")
        self.caption_label.setMinimumWidth(360)
        self.caption_label.setStyleSheet("color: #444;")
        self.statusBar().addPermanentWidget(self.caption_label, 1)

    def _build_input_group(self) -> QGroupBox:
        input_group = QGroupBox(tr("group_input"))
        input_form = QFormLayout(input_group)

        self.mic_radio = QRadioButton(tr("src_mic"))
        self.loopback_radio = QRadioButton(tr("src_loopback"))
        self.both_radio = QRadioButton(tr("src_both"))
        self.audio_group = QButtonGroup(self)
        for button in (self.mic_radio, self.loopback_radio, self.both_radio):
            self.audio_group.addButton(button)
            button.toggled.connect(self._on_audio_source_changed)
        input_form.addRow(tr("lbl_audio_source"), self.mic_radio)
        input_form.addRow("", self.loopback_radio)
        input_form.addRow("", self.both_radio)

        device_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.refresh_button = QPushButton(tr("btn_refresh"))
        self.refresh_button.clicked.connect(self._refresh_devices)
        device_row.addWidget(self.device_combo, 1)
        device_row.addWidget(self.refresh_button)
        input_form.addRow(tr("lbl_mic"), device_row)

        loopback_row = QHBoxLayout()
        self.loopback_combo = QComboBox()
        self.loopback_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.loopback_refresh_button = QPushButton(tr("btn_refresh"))
        self.loopback_refresh_button.clicked.connect(self._refresh_loopback_devices)
        loopback_row.addWidget(self.loopback_combo, 1)
        loopback_row.addWidget(self.loopback_refresh_button)
        input_form.addRow(tr("lbl_output_device"), loopback_row)
        self.loopback_combo.currentIndexChanged.connect(self._on_audio_source_changed)

        self.loopback_hint = QLabel()
        self.loopback_hint.setStyleSheet("color: gray; font-size: 11px;")
        self.loopback_hint.setWordWrap(True)
        input_form.addRow("", self.loopback_hint)

        level_row = QHBoxLayout()
        self.level_meter = LevelMeter()
        self.test_button = QPushButton(tr("btn_test_input"))
        self.test_button.setToolTip(tr("test_input_tip"))
        self.test_button.clicked.connect(self._test_input)
        self._test_button = self.test_button
        level_row.addWidget(self.level_meter, 1)
        level_row.addWidget(self.test_button)
        input_form.addRow(tr("lbl_input_level"), level_row)

        self.src_combo = QComboBox()
        for label, code in SOURCE_LANGUAGES:
            self.src_combo.addItem(label, code)
        self.tgt_combo = QComboBox()
        for label, code in TARGET_LANGUAGES:
            self.tgt_combo.addItem(label, code)
        self.src_combo.currentIndexChanged.connect(self._on_language_changed)
        self.tgt_combo.currentIndexChanged.connect(self._on_language_changed)
        input_form.addRow(tr("lbl_spoken_lang"), self.src_combo)
        input_form.addRow(tr("lbl_translate_to"), self.tgt_combo)
        lang_hint = QLabel(tr("lbl_lang_hint"))
        lang_hint.setStyleSheet("color: gray; font-size: 11px;")
        input_form.addRow("", lang_hint)
        return input_group

    def _build_models_group(self) -> QGroupBox:
        model_group = QGroupBox(tr("group_models"))
        model_form = QFormLayout(model_group)

        self.model_combo = QComboBox()
        for name in WHISPER_MODELS:
            self.model_combo.addItem(tr("auto_model") if name == "auto" else name, name)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        model_form.addRow(tr("lbl_whisper"), self.model_combo)

        self.model_status_label = QLabel()
        self.model_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.model_status_label.setWordWrap(True)
        model_form.addRow("", self.model_status_label)

        self.translation_path_label = QLabel()
        self.translation_path_label.setStyleSheet("color: #666; font-size: 11px;")
        self.translation_path_label.setWordWrap(True)
        model_form.addRow(tr("lbl_translation"), self.translation_path_label)

        self.mt_status_label = QLabel()
        self.mt_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.mt_status_label.setWordWrap(True)
        model_form.addRow("", self.mt_status_label)

        self.manage_models_button = QPushButton(tr("lbl_manage_models"))
        self.manage_models_button.clicked.connect(self._open_models_dialog)
        model_form.addRow("", self.manage_models_button)
        return model_group

    def _build_output_group(self) -> QGroupBox:
        output_group = QGroupBox(tr("group_output"))
        output_form = QFormLayout(output_group)

        self.overlay_mode_radio = QRadioButton(tr("mode_overlay"))
        self.paste_mode_radio = QRadioButton(tr("mode_paste"))
        self.mode_group = QButtonGroup(self)
        for button in (self.overlay_mode_radio, self.paste_mode_radio):
            self.mode_group.addButton(button)
            button.toggled.connect(self._on_output_mode_changed)
        output_form.addRow("", self.overlay_mode_radio)
        output_form.addRow("", self.paste_mode_radio)

        self.screen_overlay_check = QCheckBox(tr("chk_screen_overlay"))
        self.screen_overlay_check.toggled.connect(self._on_output_mode_changed)
        output_form.addRow("", self.screen_overlay_check)

        self.tts_check = QCheckBox(tr("chk_tts"))
        self.tts_check.toggled.connect(self._on_output_mode_changed)
        output_form.addRow("", self.tts_check)

        self.translate_check = QCheckBox(tr("chk_translate"))
        self.translate_check.toggled.connect(self._on_output_mode_changed)
        output_form.addRow("", self.translate_check)
        return output_group

    # -- config <-> ui -------------------------------------------------------
    def _load_config_into_ui(self) -> None:
        self._refresh_devices()
        self._refresh_loopback_devices()
        self._select_combo_by_data(self.src_combo, self.cfg.src_lang)
        self._select_combo_by_data(self.tgt_combo, self.cfg.tgt_lang)
        self._select_combo_by_data(self.model_combo, self.cfg.whisper_model)
        path = self._translation_path_keys()
        if path:
            self.cfg.translation_model = path[0]

        self.mic_radio.setChecked(self.cfg.audio_source == "mic")
        self.loopback_radio.setChecked(self.cfg.audio_source == "loopback")
        self.both_radio.setChecked(self.cfg.audio_source == "both")
        if self.cfg.audio_source not in ("mic", "loopback", "both"):
            self.mic_radio.setChecked(True)
        self._sync_audio_source_controls()

        self.overlay_mode_radio.setChecked(self.cfg.output_mode != "paste")
        self.paste_mode_radio.setChecked(self.cfg.output_mode == "paste")
        self.translate_check.setChecked(self.cfg.translate_enabled)
        self.screen_overlay_check.setChecked(self.cfg.screen_overlay_enabled)
        self.tts_check.setChecked(self.cfg.tts_enabled)

        self.overlay.set_config(self.cfg.overlay.to_payload())
        self._update_hotkey_label()
        self._refresh_model_status()
        self._loading = False
        self._set_state("idle")

    def _update_hotkey_label(self) -> None:
        self.hotkey_label.setText(tr("hotkey_line", hk=self.cfg.hotkey.upper()))

    @staticmethod
    def _select_combo_by_data(combo: QComboBox, data: str) -> None:
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _refresh_devices(self) -> None:
        current = self.device_combo.currentData()
        self.device_combo.clear()
        self.device_combo.addItem(tr("opt_system_default"), "")
        default_index = None
        for dev in list_input_devices():
            self.device_combo.addItem(dev.name, dev.key)
            if dev.is_default:
                default_index = dev.index
        target = current if current else self.cfg.device_id
        if target:
            idx = self.device_combo.findData(target)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        elif default_index is not None:
            idx = self.device_combo.findData(str(default_index))
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)

    def _refresh_loopback_devices(self) -> None:
        current = self.loopback_combo.currentData()
        self.loopback_combo.clear()
        self.loopback_combo.addItem(tr("opt_auto_output"), "")
        devices = list_output_devices()
        for dev in devices:
            self.loopback_combo.addItem(dev.name, dev.key)
        target = current if current else self.cfg.loopback_device_id
        if target:
            idx = self.loopback_combo.findData(target)
            if idx >= 0:
                self.loopback_combo.setCurrentIndex(idx)
        if devices:
            self.loopback_hint.setText(tr("loopback_hint_ok"))
            self.loopback_radio.setEnabled(True)
            self.both_radio.setEnabled(True)
            self.loopback_radio.setToolTip("")
        else:
            self.loopback_hint.setText(
                tr("loopback_hint_unavailable")
                if not output_capture_available()
                else tr("loopback_hint_none")
            )
            self.loopback_radio.setEnabled(False)
            self.both_radio.setEnabled(False)
            self.loopback_radio.setToolTip(tr("loopback_hint_none"))
        self._sync_audio_source_controls()

    def _sync_audio_source_controls(self) -> None:
        loopback = self.loopback_radio.isChecked()
        both = self.both_radio.isChecked()
        mic_only = self.mic_radio.isChecked()
        self.device_combo.setEnabled(mic_only or both)
        self.refresh_button.setEnabled(mic_only or both)
        has_devices = self.loopback_combo.count() > 1
        self.loopback_combo.setEnabled((loopback or both) and has_devices)
        self.loopback_refresh_button.setEnabled(loopback or both)

    @Slot()
    def _on_audio_source_changed(self) -> None:
        self._sync_audio_source_controls()
        if self._loading:
            return
        if self.loopback_radio.isChecked():
            self.cfg.audio_source = "loopback"
        elif self.both_radio.isChecked():
            self.cfg.audio_source = "both"
        else:
            self.cfg.audio_source = "mic"
        self.cfg.loopback_device_id = self.loopback_combo.currentData() or ""
        self._save_timer.start()

    @Slot()
    def _on_output_mode_changed(self) -> None:
        if self._loading:
            return
        self.cfg.output_mode = "paste" if self.paste_mode_radio.isChecked() else "overlay"
        self.cfg.translate_enabled = self.translate_check.isChecked()
        self.cfg.screen_overlay_enabled = self.screen_overlay_check.isChecked()
        self.cfg.tts_enabled = self.tts_check.isChecked()
        self._refresh_model_status()
        self._save_timer.start()

    def _set_state(self, state: str) -> None:
        colors = {
            "idle": "#888888",
            "loading": "#e67e22",
            "live": "#27ae60",
            "muted": "#c0392b",
            "stopped": "#888888",
            "error": "#c0392b",
        }
        self._state = state
        key = {
            "idle": "state_idle",
            "loading": "state_loading",
            "live": "state_live",
            "muted": "state_muted",
            "stopped": "state_stopped",
            "error": "state_error",
        }.get(state, "state_idle")
        self.state_label.setText("● " + tr(key))
        self.state_label.setStyleSheet(
            f"color: {colors.get(state, '#888888')}; font-weight: 600; padding: 0 6px;"
        )

    def _translation_path_keys(self) -> list[str]:
        if not self.cfg.translate_enabled:
            return []
        return find_translation_path(self.cfg.src_lang, self.cfg.tgt_lang)

    @Slot()
    def _on_language_changed(self) -> None:
        if self._loading:
            return
        self.cfg.src_lang = self.src_combo.currentData()
        self.cfg.tgt_lang = self.tgt_combo.currentData()
        path = self._translation_path_keys()
        if path:
            self.cfg.translation_model = path[0]
        self._refresh_model_status()
        self._save_timer.start()

    @Slot()
    def _on_model_changed(self) -> None:
        if self._loading:
            return
        self.cfg.whisper_model = self.model_combo.currentData()
        self._refresh_model_status()
        self._save_timer.start()

    def _save_config(self) -> None:
        self.cfg.device_id = self.device_combo.currentData() or ""
        self.cfg.loopback_device_id = self.loopback_combo.currentData() or ""
        save_config(self.cfg)

    # -- settings ------------------------------------------------------------
    @Slot()
    def open_settings(self) -> None:
        self._settings = SettingsDialog(self)
        self._settings.exec()
        self._settings = None

    def settings_changed(self) -> None:
        """Called by the Settings dialog after any change."""
        self.overlay.set_config(self.cfg.overlay.to_payload())
        self._update_hotkey_label()
        self._refresh_model_status()
        self._save_timer.start()

    def apply_hotkey(self, text: str) -> None:
        text = (text or "").strip().lower()
        try:
            parse_hotkey(text)
        except ValueError:
            self.hotkey_edit_reset()
            self.statusBar().showMessage(f"Invalid hotkey: {text!r}", 4000)
            return
        self.cfg.hotkey = text
        self._update_hotkey_label()
        self._save_timer.start()

    def hotkey_edit_reset(self) -> None:
        if self._settings is not None:
            self._settings.hotkey_edit.setText(self.cfg.hotkey)

    def restart_overlay_server(self) -> None:
        self.overlay.stop()
        self.overlay = OverlayServer(OVERLAY_DIR, self.cfg.overlay_port)
        self.overlay.set_config(self.cfg.overlay.to_payload())
        self.overlay.start()
        self.statusBar().showMessage(f"Overlay server now on {self.overlay.url}", 4000)

    # -- models --------------------------------------------------------------
    def _gpu(self) -> GpuInfo | None:
        if not self._gpu_detected:
            self._gpu_cache = detect_gpu()
            self._gpu_detected = True
        return self._gpu_cache

    def _resolve_selected_model(self) -> tuple[str, str, str, GpuInfo | None]:
        gpu = self._gpu()
        req_dev = self.cfg.device_mode or "auto"
        req_comp = self.cfg.compute_mode or "auto"
        device, compute = resolve_device_compute(req_dev, req_comp, gpu)
        requested = self.model_combo.currentData() or self.cfg.whisper_model
        return resolve_model(requested, device, gpu), device, compute, gpu

    def _models_dir(self):
        return resolved_models_dir(self.cfg)

    def _whisper_info(self, model: str) -> ModelInfo:
        if self.cfg.whisper_model_path:
            return custom_whisper_info(self.cfg.whisper_model_path)
        return whisper_model_info(model, self._models_dir())

    def _translation_info(self) -> ModelInfo:
        if self.cfg.translation_model_path:
            return custom_translation_info(self.cfg.translation_model_path)
        return translation_model_info(self.cfg.translation_model, self._models_dir())

    def _refresh_model_status(self) -> None:
        model, device, _compute, _gpu = self._resolve_selected_model()

        whisper = self._whisper_info(model)
        if self.cfg.whisper_model_path:
            state = tr("status_found") if whisper.downloaded else tr("status_invalid_whisper")
            self.model_status_label.setText(f"{tr('status_custom_on')} {device} — {state}")
        elif whisper.downloaded:
            self.model_status_label.setText(f"“{model}” {tr('status_on')} {device} — {tr('status_downloaded')}")
        else:
            self.model_status_label.setText(
                f"“{model}” {tr('status_on')} {device} — {tr('status_not_downloaded')} ({whisper.size_text})"
            )

        if not self.cfg.translate_enabled:
            self.translation_path_label.setText(tr("status_translation_off"))
            self.mt_status_label.setText("")
            return

        if self.cfg.translation_model_path:
            info = custom_translation_info(self.cfg.translation_model_path)
            state = tr("status_found") if info.downloaded else tr("status_invalid_mt")
            self.translation_path_label.setText(tr("status_custom_folder"))
            self.mt_status_label.setText(state)
            return

        path = self._translation_path_keys()
        if not path:
            self.translation_path_label.setText(tr("status_no_model_for", pair=f"{self.cfg.src_lang} → {self.cfg.tgt_lang}"))
            self.mt_status_label.setText("")
            return

        self.translation_path_label.setText(path_description(path))
        missing = missing_keys_for_path(path, self._models_dir())
        if not missing:
            self.mt_status_label.setText(tr("status_all_downloaded"))
        else:
            labels = ", ".join(translation_model_info(k, self._models_dir()).label for k in missing)
            self.mt_status_label.setText(f"{tr('status_not_downloaded')}: {labels}")

    @Slot()
    def _open_models_dialog(self) -> None:
        dialog = ModelsDialog(self.cfg, self)
        dialog.exec()
        if dialog.changed:
            save_config(self.cfg)
        self._refresh_model_status()

    # -- actions -------------------------------------------------------------
    def copy_obs_url(self) -> None:
        QGuiApplication.clipboard().setText(self.overlay.url)
        self.statusBar().showMessage(tr("msg_copied_url", url=self.overlay.url), 3000)

    def open_preview(self) -> None:
        QDesktopServices.openUrl(QUrl(self.overlay.url))

    def _test_input(self) -> None:
        if self.pipeline is not None and self.pipeline.is_running:
            self.statusBar().showMessage(tr("test_use_live"), 4000)
            return
        if self._monitor is not None:
            return
        self.level_meter.reset()
        self.test_button.setEnabled(False)
        self.test_button.setText(tr("test_running"))
        self.statusBar().showMessage(tr("test_running"), 0)
        monitor = InputMonitor(self.cfg)
        monitor.level.connect(self.level_meter.set_level)
        monitor.finished.connect(self._on_test_finished)
        self._monitor = monitor
        monitor.start(3.0)

    def _cancel_input_test(self) -> None:
        if self._monitor is None:
            return
        monitor = self._monitor
        self._monitor = None
        monitor.stop()
        monitor.deleteLater()
        self.level_meter.reset()
        self.test_button.setEnabled(True)
        self.test_button.setText(tr("btn_test_input"))

    @Slot(bool, float)
    def _on_test_finished(self, detected: bool, peak: float) -> None:
        if self._monitor is not None:
            monitor = self._monitor
            self._monitor = None
            monitor.deleteLater()
        self.test_button.setEnabled(True)
        self.test_button.setText(tr("btn_test_input"))
        QTimer.singleShot(1200, self.level_meter.reset)
        if detected:
            self.statusBar().showMessage(tr("test_detected"), 5000)
        else:
            self.statusBar().showMessage(tr("test_silent"), 6000)

    def send_test_subtitle(self) -> None:
        target, source = SAMPLE_LINES[self._sample_index % len(SAMPLE_LINES)]
        self._sample_index += 1
        event = {"id": "test", "src": source, "tgt": target, "ts": 0}
        self.overlay.set_caption(event)
        self._on_caption(event)
        self.statusBar().showMessage(tr("msg_sent_test"), 3000)
        QTimer.singleShot(int(self.cfg.overlay.auto_hide_sec * 1000) + 300, self._clear_test_subtitle)

    def _clear_test_subtitle(self) -> None:
        if self.pipeline is None:
            self.overlay.set_caption(None)

    def _toggle_mute(self) -> None:
        if self.pipeline is None:
            self.statusBar().showMessage(tr("msg_start_first"), 3000)
            return
        muted = not self.pipeline.is_muted
        self.pipeline.set_muted(muted)
        if muted:
            self.statusBar().showMessage(tr("msg_muted"))
            self._set_state("muted")
            if self._screen_overlay is not None:
                self._screen_overlay.clear()
            self._stop_tts()
        else:
            self.statusBar().showMessage(tr("msg_live"))
            self._set_state("live")
        self._update_tray_labels()

    @staticmethod
    def _stop_tts() -> None:
        try:
            from .. import tts

            tts.stop()
        except Exception:  # noqa: BLE001
            pass

    def _open_config_folder(self) -> None:
        from ..config import CONFIG_PATH

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH.parent)))

    def _open_models_folder(self) -> None:
        path = self._models_dir()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # -- system tray ---------------------------------------------------------
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(QIcon(str(ICON_ICO)), self)
        self._tray.setToolTip(APP_NAME)

        menu = QMenu()
        self._tray_start_action = QAction(tr("tray_start"), self)
        self._tray_start_action.triggered.connect(self._tray_toggle)
        self._tray_mute_action = QAction(tr("tray_mute"), self)
        self._tray_mute_action.triggered.connect(self._toggle_mute)
        show_action = QAction(tr("tray_show"), self)
        show_action.triggered.connect(self._show_window)
        preview_action = QAction(tr("tray_preview"), self)
        preview_action.triggered.connect(self.open_preview)
        quit_action = QAction(tr("tray_quit"), self)
        quit_action.triggered.connect(self._quit)

        menu.addAction(self._tray_start_action)
        menu.addAction(self._tray_mute_action)
        menu.addSeparator()
        menu.addAction(show_action)
        menu.addAction(preview_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _update_tray_labels(self) -> None:
        if self._tray_start_action is not None:
            running = self.pipeline is not None and self.pipeline.is_running
            self._tray_start_action.setText(tr("tray_stop") if running else tr("tray_start"))
        if self._tray_mute_action is not None:
            muted = self.pipeline is not None and self.pipeline.is_muted
            self._tray_mute_action.setText(tr("tray_unmute") if muted else tr("tray_mute"))

    @Slot()
    def _tray_toggle(self) -> None:
        self.start_button.setChecked(not self.start_button.isChecked())

    def _on_tray_activated(self, reason) -> None:  # noqa: ANN001
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self._force_quit = True
        self.close()

    # -- pipeline control ----------------------------------------------------
    @Slot(bool)
    def _on_start_toggled(self, checked: bool) -> None:
        if checked:
            self._begin_start()
        else:
            self._stop()

    def _auto_start(self) -> None:
        if self.start_button.isChecked():
            return
        if self._custom_path_problem() or self._missing_models():
            self.statusBar().showMessage(tr("msg_autostart_skipped"), 6000)
            return
        self.start_button.setChecked(True)

    def _begin_start(self) -> None:
        self.cfg.device_id = self.device_combo.currentData() or ""
        self.cfg.loopback_device_id = self.loopback_combo.currentData() or ""
        if self.loopback_radio.isChecked():
            self.cfg.audio_source = "loopback"
        elif self.both_radio.isChecked():
            self.cfg.audio_source = "both"
        else:
            self.cfg.audio_source = "mic"
        self.cfg.output_mode = "paste" if self.paste_mode_radio.isChecked() else "overlay"
        self.cfg.translate_enabled = self.translate_check.isChecked()
        self.cfg.screen_overlay_enabled = self.screen_overlay_check.isChecked()
        self.cfg.tts_enabled = self.tts_check.isChecked()
        self.cfg.src_lang = self.src_combo.currentData()
        self.cfg.tgt_lang = self.tgt_combo.currentData()
        path = self._translation_path_keys()
        self.cfg.translation_model = path[0] if path else DEFAULT_TRANSLATION_KEY
        self.cfg.whisper_model = self.model_combo.currentData()
        self.overlay.set_config(self.cfg.overlay.to_payload())
        save_config(self.cfg)

        if self.cfg.audio_source in ("loopback", "both") and not list_loopback_devices():
            QMessageBox.warning(
                self,
                "Cyctitles",
                "System-output capture is selected but no output device was found.\n\n"
                "Connect your speakers/interface and press Refresh under “Output device”.",
            )
            self._cancel_start()
            return

        problem = self._custom_path_problem()
        if problem:
            QMessageBox.warning(self, "Cyctitles", problem)
            self._cancel_start()
            return

        missing = self._missing_models()
        if missing and not self._confirm_and_download(missing):
            self._cancel_start()
            return

        self._launch_pipeline()

    def _custom_path_problem(self) -> str | None:
        if self.cfg.whisper_model_path:
            info = custom_whisper_info(self.cfg.whisper_model_path)
            if not info.downloaded:
                return (
                    "The custom Whisper folder does not contain model.bin:\n"
                    f"{info.directory}\n\n"
                    "Fix it in Models → Manage models…, or clear the custom path."
                )
        if self.cfg.translation_model_path:
            info = custom_translation_info(self.cfg.translation_model_path)
            if not info.downloaded:
                return (
                    "The custom translation folder is missing model.bin / "
                    "src.spm.model / tgt.spm.model:\n"
                    f"{info.directory}\n\n"
                    "Fix it in Models → Manage models…, or clear the custom path."
                )
        return None

    def _missing_models(self) -> list[ModelInfo]:
        model, *_ = self._resolve_selected_model()
        infos: list[ModelInfo] = []
        whisper = self._whisper_info(model)
        if not whisper.downloaded and whisper.repo_id != CUSTOM_REPO:
            infos.append(whisper)
        if self.cfg.translate_enabled:
            path = self._translation_path_keys()
            for key in missing_keys_for_path(path, self._models_dir()):
                infos.append(translation_model_info(key, self._models_dir()))
        return infos

    def _confirm_and_download(self, infos: list[ModelInfo]) -> bool:
        dialog = MissingModelsDialog(infos, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        ok, error = run_download(infos, self._models_dir(), self)
        self._refresh_model_status()
        if not ok:
            QMessageBox.warning(self, "Cyctitles", tr("msg_download_failed", err=error))
        return ok

    def _cancel_start(self) -> None:
        self.start_button.blockSignals(True)
        self.start_button.setChecked(False)
        self.start_button.blockSignals(False)
        self.start_button.setText(tr("btn_start"))
        self._set_controls_enabled(True)
        self._update_tray_labels()
        self._set_state("idle")
        self.statusBar().showMessage(tr("msg_start_cancelled"), 5000)

    def _launch_pipeline(self) -> None:
        self._cancel_input_test()
        self._set_controls_enabled(False)
        self.start_button.setText(tr("btn_stop"))
        self._set_state("loading")

        self.pipeline = Pipeline(self.cfg, self.overlay)
        self.pipeline.status.connect(self.statusBar().showMessage)
        self.pipeline.caption.connect(self._on_caption)
        self.pipeline.ready.connect(self._on_ready)
        self.pipeline.error.connect(self._on_error)
        self.pipeline.stopped.connect(self._on_stopped)
        self.pipeline.level.connect(self.level_meter.set_level)
        self.pipeline.start()

        try:
            self.hotkey = GlobalHotkey(self.cfg.hotkey, self._toggle_mute)
            self.hotkey.start()
        except Exception as exc:  # noqa: BLE001
            self.hotkey = None
            self.statusBar().showMessage(f"Hotkey unavailable: {exc}", 5000)

        self._update_tray_labels()

    def _stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.mic_radio,
            self.loopback_radio,
            self.both_radio,
            self.device_combo,
            self.refresh_button,
            self.loopback_combo,
            self.loopback_refresh_button,
            self.src_combo,
            self.tgt_combo,
            self.model_combo,
            self.overlay_mode_radio,
            self.paste_mode_radio,
            self.translate_check,
            self.screen_overlay_check,
            self.tts_check,
            self.manage_models_button,
            self.test_button,
        ):
            widget.setEnabled(enabled)
        if enabled:
            self._sync_audio_source_controls()
            self._refresh_model_status()

    @Slot(dict)
    def _on_ready(self, info: dict) -> None:
        parts = [f"{info['gpu']}", f"whisper {info['model']} ({info['device']}/{info['compute']})"]
        if self.cfg.output_mode == "paste":
            parts.append(tr("mode_dictation"))
        elif info.get("translation") and info["translation"] != "off":
            parts.append(f"MT {info['translation']}")
        self.info_label.setText(tr("msg_ready", details=" · ".join(parts)))
        self.statusBar().showMessage(tr("msg_listening"))
        self._set_state("live")
        self._update_tray_labels()

    @Slot(dict)
    def _on_caption(self, caption: dict) -> None:
        preview = caption.get("tgt", "")
        if len(preview) > 80:
            preview = preview[:77] + "…"
        self.caption_label.setText(preview)

        if self.cfg.screen_overlay_enabled and self._screen_overlay is not None:
            self._screen_overlay.set_auto_hide(self.cfg.overlay.auto_hide_sec)
            self._screen_overlay.show_caption(
                caption.get("tgt", ""), self.cfg.overlay.font_scale
            )
        if self.cfg.tts_enabled and caption.get("id") != "test":
            from .. import tts

            tts.speak(caption.get("tgt", ""), self.cfg.tts_rate, self.cfg.tts_volume)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, "Cyctitles", message)
        self.statusBar().showMessage(message, 8000)
        self._set_state("error")

    @Slot()
    def _on_stopped(self) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
        self.pipeline = None
        self.start_button.setChecked(False)
        self.start_button.setText(tr("btn_start"))
        self.level_meter.reset()
        self._set_controls_enabled(True)
        self._update_tray_labels()
        self.statusBar().showMessage(tr("msg_stopped"))
        self._set_state("stopped")
        if self._screen_overlay is not None:
            self._screen_overlay.clear()
        self._stop_tts()

    # -- misc ----------------------------------------------------------------
    def show_obs_help(self) -> None:
        QMessageBox.information(
            self,
            tr("obs_help_title"),
            tr("obs_help_body", url=self.overlay.url),
        )

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _show_how_to(self) -> None:
        HowToUseDialog(str(self._models_dir()), self).exec()

    def _restore_geometry(self) -> None:
        if self.cfg.window_geometry:
            try:
                from PySide6.QtCore import QByteArray

                self.restoreGeometry(QByteArray.fromBase64(self.cfg.window_geometry.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        if self._tray is not None and self.cfg.minimize_to_tray and not self._force_quit:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "Cyctitles is still running",
                "Subtitles keep working. Right-click the tray icon and choose Quit to exit.",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )
            return

        from PySide6.QtCore import QByteArray

        try:
            geom = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.cfg.window_geometry = geom
        except Exception:  # noqa: BLE001
            pass
        self.cfg.device_id = self.device_combo.currentData() or ""
        self.cfg.loopback_device_id = self.loopback_combo.currentData() or ""
        save_config(self.cfg)
        if self.pipeline is not None:
            self.pipeline.stop()
        if self.hotkey is not None:
            self.hotkey.stop()
        self.overlay.stop()
        if self._screen_overlay is not None:
            self._screen_overlay.close()
        if self._tray is not None:
            self._tray.hide()
        super().closeEvent(event)
