"""Tabbed Settings dialog.

The main window keeps only the essentials (Input, Models, Output mode); every
other option lives here, grouped into tabs. Changes apply immediately: the
dialog writes to the shared ``Config`` and calls ``owner.settings_changed()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..i18n import tr
from ..transcriber import detect_gpu, resolve_device_compute

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow


def _slider_row(slider: QSlider, label: QLabel) -> QWidget:
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(slider, 1)
    h.addWidget(label)
    return row


class SettingsDialog(QDialog):
    def __init__(self, owner: "MainWindow") -> None:
        super().__init__(owner)
        self.owner = owner
        self.cfg: Config = owner.cfg
        self._loading = True

        self.setWindowTitle(tr("settings_title"))
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_subtitles(), tr("tab_subtitles"))
        self.tabs.addTab(self._tab_performance(), tr("tab_performance"))
        self.tabs.addTab(self._tab_processing(), tr("tab_processing"))
        self.tabs.addTab(self._tab_speech(), tr("tab_speech"))
        self.tabs.addTab(self._tab_behavior(), tr("tab_behavior"))
        self.tabs.addTab(self._tab_appearance(), tr("tab_appearance"))
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox()
        close = buttons.addButton(tr("btn_close"), QDialogButtonBox.ButtonRole.AcceptRole)
        close.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._load()
        self._loading = False

    # -- helpers -------------------------------------------------------------
    def _changed(self) -> None:
        if self._loading:
            return
        self.owner.settings_changed()

    def _slider(self, lo: int, hi: int, suffix: str) -> tuple[QSlider, QLabel]:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        label = QLabel()
        label.setMinimumWidth(48)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda v, lb=label, s=suffix: lb.setText(f"{v}{s}"))
        return slider, label

    def _color_button(self, getter, setter) -> QPushButton:  # noqa: ANN001
        button = QPushButton()
        button.setFixedWidth(96)
        self._set_color_button(button, getter())

        def choose() -> None:
            color = QColorDialog.getColor(Qt.GlobalColor.white, self, "Choose color")
            if color.isValid():
                setter(color.name())
                self._set_color_button(button, color.name())
                self._changed()

        button.clicked.connect(choose)
        return button

    @staticmethod
    def _set_color_button(button: QPushButton, hex_color: str) -> None:
        from PySide6.QtGui import QColor

        color = QColor(hex_color)
        lum = (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255.0
        fg = "#000000" if lum > 0.6 else "#ffffff"
        button.setText(hex_color)
        button.setStyleSheet(
            f"background:{hex_color};color:{fg};border:1px solid #888;border-radius:3px;padding:2px;"
        )

    def _tab_appearance(self) -> QWidget:
        ov = self.cfg.overlay
        w = QWidget()
        form = QFormLayout(w)

        from ..i18n import UI_LANGUAGES

        self.ui_lang_combo2 = QComboBox()
        for label, code in UI_LANGUAGES:
            self.ui_lang_combo2.addItem(label, code)
        self.ui_lang_combo2.currentIndexChanged.connect(self._on_behavior_changed)
        form.addRow(tr("set_app_lang"), self.ui_lang_combo2)

        self.theme_combo2 = QComboBox()
        for item in (
            (tr("opt_theme_auto"), "auto"),
            (tr("opt_theme_light"), "light"),
            (tr("opt_theme_dark"), "dark"),
        ):
            self.theme_combo2.addItem(item[0], item[1])
        self.theme_combo2.currentIndexChanged.connect(self._on_behavior_changed)
        form.addRow(tr("set_theme"), self.theme_combo2)
        return w

    # -- tabs ----------------------------------------------------------------
    def _tab_subtitles(self) -> QWidget:
        ov = self.cfg.overlay
        w = QWidget()
        form = QFormLayout(w)

        self.opacity_slider, self.opacity_label = self._slider(0, 100, "%")
        self.opacity_slider.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_bg_opacity"), _slider_row(self.opacity_slider, self.opacity_label))

        self.font_slider, self.font_label = self._slider(60, 160, "%")
        self.font_slider.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_font_size"), _slider_row(self.font_slider, self.font_label))

        self.max_lines_spin = QSpinBox()
        self.max_lines_spin.setRange(1, 5)
        self.max_lines_spin.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_max_lines"), self.max_lines_spin)

        self.position_combo = QComboBox()
        self.position_combo.addItem(tr("opt_bottom"), "bottom")
        self.position_combo.addItem(tr("opt_top"), "top")
        self.position_combo.currentIndexChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_position"), self.position_combo)

        self.text_color_button = self._color_button(
            lambda: self.cfg.overlay.text_color,
            lambda v: setattr(self.cfg.overlay, "text_color", v),
        )
        form.addRow(tr("set_text_color"), self.text_color_button)

        self.bg_color_button = self._color_button(
            lambda: self.cfg.overlay.background,
            lambda v: setattr(self.cfg.overlay, "background", v),
        )
        form.addRow(tr("set_box_color"), self.bg_color_button)

        self.outline_spin = QDoubleSpinBox()
        self.outline_spin.setRange(0.0, 0.2)
        self.outline_spin.setSingleStep(0.01)
        self.outline_spin.setDecimals(2)
        self.outline_spin.setSuffix(" px")
        self.outline_spin.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_outline"), self.outline_spin)

        self.outline_color_button = self._color_button(
            lambda: self.cfg.overlay.outline_color,
            lambda v: setattr(self.cfg.overlay, "outline_color", v),
        )
        form.addRow(tr("set_outline_color"), self.outline_color_button)

        self.weight_combo = QComboBox()
        self.weight_combo.addItem(tr("opt_regular"), 400)
        self.weight_combo.addItem(tr("opt_semibold"), 600)
        self.weight_combo.addItem(tr("opt_bold"), 700)
        self.weight_combo.currentIndexChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_font_weight"), self.weight_combo)

        self.animation_combo = QComboBox()
        self.animation_combo.addItem(tr("opt_fade"), "fade")
        self.animation_combo.addItem(tr("opt_slide_up"), "slide-up")
        self.animation_combo.addItem(tr("opt_slide_down"), "slide-down")
        self.animation_combo.currentIndexChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_animation"), self.animation_combo)

        self.anim_duration_spin = QDoubleSpinBox()
        self.anim_duration_spin.setRange(0.05, 2.0)
        self.anim_duration_spin.setSingleStep(0.05)
        self.anim_duration_spin.setSuffix(" s")
        self.anim_duration_spin.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_anim_speed"), self.anim_duration_spin)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem(tr("preset_custom"), "custom")
        self.preset_combo.addItem(tr("preset_default"), "default")
        self.preset_combo.addItem(tr("preset_minimal"), "minimal")
        self.preset_combo.addItem(tr("preset_bold"), "bold")
        self.preset_combo.addItem(tr("preset_cinematic"), "cinematic")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow(tr("set_preset"), self.preset_combo)

        self.show_original_check = QCheckBox(tr("set_show_original"))
        self.show_original_check.toggled.connect(self._on_overlay_changed)
        form.addRow("", self.show_original_check)

        self.orig_slider, self.orig_label = self._slider(40, 100, "%")
        self.orig_slider.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_original_size"), _slider_row(self.orig_slider, self.orig_label))

        self.autohide_spin = QDoubleSpinBox()
        self.autohide_spin.setRange(1.0, 30.0)
        self.autohide_spin.setSingleStep(0.5)
        self.autohide_spin.setSuffix(" s")
        self.autohide_spin.valueChanged.connect(self._on_overlay_changed)
        form.addRow(tr("set_hide_after"), self.autohide_spin)

        self.url_label = QLabel("-")
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_label.setStyleSheet("font-family: Consolas, monospace;")
        form.addRow(tr("set_obs_url"), self.url_label)

        buttons = QHBoxLayout()
        for text, cb in (
            (tr("btn_send_test"), self.owner.send_test_subtitle),
            (tr("btn_preview"), self.owner.open_preview),
            (tr("btn_copy_url"), self.owner.copy_obs_url),
            (tr("btn_obs_help"), self.owner.show_obs_help),
        ):
            b = QPushButton(text)
            b.clicked.connect(cb)
            buttons.addWidget(b)
        form.addRow("", buttons)
        return w

    def _tab_performance(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.device_mode_combo = QComboBox()
        self.device_mode_combo.addItem(tr("opt_auto_gpu"), "auto")
        self.device_mode_combo.addItem(tr("opt_force_cpu"), "cpu")
        self.device_mode_combo.currentIndexChanged.connect(self._on_perf_changed)
        form.addRow(tr("set_device"), self.device_mode_combo)

        self.compute_mode_combo = QComboBox()
        self.compute_mode_combo.addItem(tr("opt_compute_auto"), "auto")
        self.compute_mode_combo.addItem(tr("opt_compute_int8"), "int8")
        self.compute_mode_combo.addItem("int8_float16", "int8_float16")
        self.compute_mode_combo.addItem("float16", "float16")
        self.compute_mode_combo.currentIndexChanged.connect(self._on_perf_changed)
        form.addRow(tr("set_compute"), self.compute_mode_combo)

        self.hardware_label = QLabel()
        self.hardware_label.setWordWrap(True)
        self.hardware_label.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", self.hardware_label)

        note = QLabel(tr("perf_note"))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", note)
        return w

    def _tab_processing(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.max_chunk_spin = QDoubleSpinBox()
        self.max_chunk_spin.setRange(2.0, 30.0)
        self.max_chunk_spin.setSingleStep(0.5)
        self.max_chunk_spin.setSuffix(" s")
        self.max_chunk_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_cut_after"), self.max_chunk_spin)

        self.min_silence_spin = QDoubleSpinBox()
        self.min_silence_spin.setRange(0.2, 2.0)
        self.min_silence_spin.setSingleStep(0.05)
        self.min_silence_spin.setSuffix(" s")
        self.min_silence_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_end_silence"), self.min_silence_spin)

        self.min_speech_spin = QDoubleSpinBox()
        self.min_speech_spin.setRange(0.1, 1.0)
        self.min_speech_spin.setSingleStep(0.05)
        self.min_speech_spin.setSuffix(" s")
        self.min_speech_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_ignore_short"), self.min_speech_spin)

        self.vad_spin = QSpinBox()
        self.vad_spin.setRange(0, 3)
        self.vad_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_vad_aggr"), self.vad_spin)

        self.vad_backend_combo = QComboBox()
        self.vad_backend_combo.addItem(tr("opt_vad_webrtc"), "webrtcvad")
        self.vad_backend_combo.addItem(tr("opt_vad_energy"), "energy")
        self.vad_backend_combo.currentIndexChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_vad_backend"), self.vad_backend_combo)

        self.energy_spin = QDoubleSpinBox()
        self.energy_spin.setRange(0.001, 0.2)
        self.energy_spin.setSingleStep(0.001)
        self.energy_spin.setDecimals(3)
        self.energy_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_energy_thresh"), self.energy_spin)

        self.max_words_spin = QSpinBox()
        self.max_words_spin.setRange(0, 200)
        self.max_words_spin.setSpecialValueText(tr("opt_no_limit"))
        self.max_words_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_max_words"), self.max_words_spin)

        self.min_chars_spin = QSpinBox()
        self.min_chars_spin.setRange(0, 40)
        self.min_chars_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_min_chars"), self.min_chars_spin)

        self.split_sentences_check = QCheckBox(tr("chk_split_sentences"))
        self.split_sentences_check.toggled.connect(self._on_processing_changed)
        form.addRow(tr("set_split_sentences"), self.split_sentences_check)

        self.capitalize_check = QCheckBox(tr("chk_capitalize"))
        self.capitalize_check.toggled.connect(self._on_processing_changed)
        form.addRow("", self.capitalize_check)

        self.dedupe_check = QCheckBox(tr("chk_dedupe"))
        self.dedupe_check.toggled.connect(self._on_processing_changed)
        form.addRow("", self.dedupe_check)

        self.dictation_combo = QComboBox()
        self.dictation_combo.addItem(tr("opt_dictation_paste"), "paste")
        self.dictation_combo.addItem(tr("opt_dictation_type"), "type")
        self.dictation_combo.currentIndexChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_dictation"), self.dictation_combo)

        self.dictation_space_check = QCheckBox(tr("chk_dictation_space"))
        self.dictation_space_check.toggled.connect(self._on_processing_changed)
        form.addRow("", self.dictation_space_check)

        self.dictation_enter_check = QCheckBox(tr("chk_dictation_enter"))
        self.dictation_enter_check.toggled.connect(self._on_processing_changed)
        form.addRow("", self.dictation_enter_check)

        self.dictation_delay_spin = QSpinBox()
        self.dictation_delay_spin.setRange(0, 200)
        self.dictation_delay_spin.setSingleStep(5)
        self.dictation_delay_spin.setSuffix(" ms")
        self.dictation_delay_spin.valueChanged.connect(self._on_processing_changed)
        form.addRow(tr("set_dictation_delay"), self.dictation_delay_spin)

        note = QLabel(tr("proc_note"))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", note)
        return w

    def _tab_speech(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.tts_rate_slider, self.tts_rate_label = self._slider(-10, 10, "")
        self.tts_rate_slider.valueChanged.connect(self._on_speech_changed)
        form.addRow(tr("set_voice_speed"), _slider_row(self.tts_rate_slider, self.tts_rate_label))

        self.tts_volume_slider, self.tts_volume_label = self._slider(0, 100, "%")
        self.tts_volume_slider.valueChanged.connect(self._on_speech_changed)
        form.addRow(
            tr("set_voice_volume"), _slider_row(self.tts_volume_slider, self.tts_volume_label)
        )

        test = QPushButton(tr("btn_test_voice"))
        test.clicked.connect(self._test_voice)
        form.addRow("", test)

        note = QLabel(tr("speech_note"))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", note)
        return w

    def _tab_behavior(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.autostart_check = QCheckBox(tr("chk_autostart"))
        self.autostart_check.toggled.connect(self._on_behavior_changed)
        form.addRow("", self.autostart_check)

        self.tray_check = QCheckBox(tr("chk_tray"))
        self.tray_check.toggled.connect(self._on_behavior_changed)
        form.addRow("", self.tray_check)

        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("ctrl+shift+s")
        self.hotkey_edit.editingFinished.connect(self._on_hotkey_changed)
        form.addRow(tr("set_hotkey"), self.hotkey_edit)

        self.overlay_port_spin = QSpinBox()
        self.overlay_port_spin.setRange(1024, 65535)
        self.overlay_port_spin.valueChanged.connect(self._on_behavior_changed)
        form.addRow(tr("set_port"), self.overlay_port_spin)

        port_note = QLabel(tr("port_note"))
        port_note.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", port_note)
        return w

    # -- load / save ---------------------------------------------------------
    def _load(self) -> None:
        ov = self.cfg.overlay
        self.opacity_slider.setValue(int(round(ov.opacity * 100)))
        self.font_slider.setValue(int(round(ov.font_scale * 100)))
        self.max_lines_spin.setValue(int(ov.max_lines))
        idx = self.position_combo.findData(ov.position)
        if idx >= 0:
            self.position_combo.setCurrentIndex(idx)
        self._set_color_button(self.text_color_button, ov.text_color)
        self._set_color_button(self.bg_color_button, ov.background)
        self._set_color_button(self.outline_color_button, getattr(ov, "outline_color", "#000000"))
        self.outline_spin.setValue(float(getattr(ov, "outline_width", 0.0)))
        widx = self.weight_combo.findData(int(getattr(ov, "font_weight", 600)))
        if widx >= 0:
            self.weight_combo.setCurrentIndex(widx)
        aidx = self.animation_combo.findData(getattr(ov, "animation", "fade"))
        if aidx >= 0:
            self.animation_combo.setCurrentIndex(aidx)
        self.anim_duration_spin.setValue(float(getattr(ov, "animation_duration", 0.25)))
        pidx = self.preset_combo.findData(getattr(ov, "preset", "custom"))
        if pidx >= 0:
            self.preset_combo.setCurrentIndex(pidx)
        self.show_original_check.setChecked(ov.show_original)
        self.orig_slider.setValue(int(round(ov.original_scale * 100)))
        self.orig_slider.setEnabled(ov.show_original)
        self.autohide_spin.setValue(ov.auto_hide_sec)
        self._update_url()

        self._select(self.device_mode_combo, self.cfg.device_mode)
        self._select(self.compute_mode_combo, self.cfg.compute_mode)
        self._update_hardware()

        self.max_chunk_spin.setValue(self.cfg.max_chunk_sec)
        self.min_silence_spin.setValue(self.cfg.min_silence_sec)
        self.min_speech_spin.setValue(self.cfg.min_speech_sec)
        self.vad_spin.setValue(int(self.cfg.vad_aggressiveness))
        self._select(self.vad_backend_combo, getattr(self.cfg, "vad_backend", "webrtcvad"))
        self.energy_spin.setValue(float(getattr(self.cfg, "vad_energy_threshold", 0.012)))
        self.max_words_spin.setValue(int(self.cfg.max_words_per_caption))
        self.min_chars_spin.setValue(int(self.cfg.min_caption_chars))
        self.split_sentences_check.setChecked(self.cfg.split_sentences)
        self.capitalize_check.setChecked(self.cfg.capitalize_sentences)
        self.dedupe_check.setChecked(self.cfg.dedupe_repeats)
        self._select(self.dictation_combo, self.cfg.dictation_method)
        self.dictation_space_check.setChecked(
            bool(getattr(self.cfg, "dictation_trailing_space", True))
        )
        self.dictation_enter_check.setChecked(
            bool(getattr(self.cfg, "dictation_enter_after", False))
        )
        self.dictation_delay_spin.setValue(
            int(getattr(self.cfg, "dictation_typing_delay_ms", 0))
        )

        self.tts_rate_slider.setValue(int(self.cfg.tts_rate))
        self.tts_volume_slider.setValue(int(self.cfg.tts_volume))

        self.autostart_check.setChecked(self.cfg.auto_start)
        self.tray_check.setChecked(self.cfg.minimize_to_tray)
        self._select(self.ui_lang_combo2, getattr(self.cfg, "ui_language", "en"))
        self._select(self.theme_combo2, getattr(self.cfg, "theme", "auto"))
        self.hotkey_edit.setText(self.cfg.hotkey)
        self.overlay_port_spin.setValue(int(self.cfg.overlay_port))

    @staticmethod
    def _select(combo: QComboBox, data: str) -> None:
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _update_url(self) -> None:
        url = getattr(self.owner.overlay, "url", "")
        self.url_label.setText(url or "-")

    def _update_hardware(self) -> None:
        cfg = self.cfg
        try:
            gpu = detect_gpu()
            device, compute = resolve_device_compute(cfg.device_mode, cfg.compute_mode, gpu)
        except Exception:  # noqa: BLE001
            self.hardware_label.setText(tr("hw_detect_failed"))
            return
        if gpu is not None:
            self.hardware_label.setText(
                tr("hw_detected_gpu", name=gpu.name, vram=gpu.vram_mb, device=device, compute=compute)
            )
        else:
            self.hardware_label.setText(
                tr("hw_no_gpu", device=device, compute=compute)
            )

    # -- change handlers -----------------------------------------------------
    def _on_overlay_changed(self) -> None:
        if self._loading:
            return
        ov = self.cfg.overlay
        ov.opacity = self.opacity_slider.value() / 100.0
        ov.font_scale = self.font_slider.value() / 100.0
        ov.max_lines = int(self.max_lines_spin.value())
        ov.position = self.position_combo.currentData()
        ov.outline_width = float(self.outline_spin.value())
        ov.font_weight = int(self.weight_combo.currentData() or 600)
        ov.animation = self.animation_combo.currentData() or "fade"
        ov.animation_duration = float(self.anim_duration_spin.value())
        ov.preset = self.preset_combo.currentData() or "custom"
        ov.show_original = self.show_original_check.isChecked()
        ov.original_scale = self.orig_slider.value() / 100.0
        ov.auto_hide_sec = float(self.autohide_spin.value())
        self.orig_slider.setEnabled(ov.show_original)
        self._changed()

    def _on_preset_changed(self) -> None:
        if self._loading:
            return
        self._apply_preset(self.preset_combo.currentData() or "custom")
        self._sync_overlay_widgets()
        self._on_overlay_changed()

    def _apply_preset(self, name: str) -> None:
        ov = self.cfg.overlay
        presets = {
            "default": dict(opacity=0.75, font_scale=1.0, max_lines=2, outline_width=0.0,
                            font_weight=600, animation="fade", animation_duration=0.25,
                            outline_color="#000000", text_color="#ffffff", background="#000000"),
            "minimal": dict(opacity=0.0, font_scale=1.0, max_lines=2, outline_width=0.04,
                            font_weight=600, animation="fade", animation_duration=0.20,
                            outline_color="#000000", text_color="#ffffff", background="#000000"),
            "bold": dict(opacity=0.85, font_scale=1.25, max_lines=2, outline_width=0.0,
                         font_weight=700, animation="slide-up", animation_duration=0.25,
                         outline_color="#000000", text_color="#ffffff", background="#000000"),
            "cinematic": dict(opacity=0.55, font_scale=1.05, max_lines=3, outline_width=0.03,
                              font_weight=400, animation="fade", animation_duration=0.5,
                              outline_color="#000000", text_color="#ffffff", background="#000000"),
        }
        for key, value in presets.get(name, {}).items():
            setattr(ov, key, value)

    def _sync_overlay_widgets(self) -> None:
        ov = self.cfg.overlay
        self.opacity_slider.setValue(int(round(ov.opacity * 100)))
        self.font_slider.setValue(int(round(ov.font_scale * 100)))
        self.max_lines_spin.setValue(int(ov.max_lines))
        self.outline_spin.setValue(float(getattr(ov, "outline_width", 0.0)))
        self._set_color_button(self.outline_color_button, getattr(ov, "outline_color", "#000000"))
        idx = self.weight_combo.findData(int(getattr(ov, "font_weight", 600)))
        if idx >= 0:
            self.weight_combo.setCurrentIndex(idx)
        idx = self.animation_combo.findData(getattr(ov, "animation", "fade"))
        if idx >= 0:
            self.animation_combo.setCurrentIndex(idx)
        self.anim_duration_spin.setValue(float(getattr(ov, "animation_duration", 0.25)))

    def _on_perf_changed(self) -> None:
        if self._loading:
            return
        self.cfg.device_mode = self.device_mode_combo.currentData()
        self.cfg.compute_mode = self.compute_mode_combo.currentData()
        self._update_hardware()
        self._changed()

    def _on_processing_changed(self) -> None:
        if self._loading:
            return
        self.cfg.max_chunk_sec = float(self.max_chunk_spin.value())
        self.cfg.min_silence_sec = float(self.min_silence_spin.value())
        self.cfg.min_speech_sec = float(self.min_speech_spin.value())
        self.cfg.vad_aggressiveness = int(self.vad_spin.value())
        self.cfg.vad_backend = self.vad_backend_combo.currentData() or "webrtcvad"
        self.cfg.vad_energy_threshold = float(self.energy_spin.value())
        self.cfg.max_words_per_caption = int(self.max_words_spin.value())
        self.cfg.min_caption_chars = int(self.min_chars_spin.value())
        self.cfg.split_sentences = self.split_sentences_check.isChecked()
        self.cfg.capitalize_sentences = self.capitalize_check.isChecked()
        self.cfg.dedupe_repeats = self.dedupe_check.isChecked()
        self.cfg.dictation_method = self.dictation_combo.currentData()
        self.cfg.dictation_trailing_space = self.dictation_space_check.isChecked()
        self.cfg.dictation_enter_after = self.dictation_enter_check.isChecked()
        self.cfg.dictation_typing_delay_ms = int(self.dictation_delay_spin.value())
        self._changed()

    def _on_speech_changed(self) -> None:
        if self._loading:
            return
        self.cfg.tts_rate = int(self.tts_rate_slider.value())
        self.cfg.tts_volume = int(self.tts_volume_slider.value())
        self._changed()

    def _on_behavior_changed(self) -> None:
        if self._loading:
            return
        self.cfg.auto_start = self.autostart_check.isChecked()
        self.cfg.minimize_to_tray = self.tray_check.isChecked()
        new_lang = self.ui_lang_combo2.currentData() or "en"
        if getattr(self.cfg, "ui_language", "en") != new_lang:
            self.cfg.ui_language = new_lang
            try:
                from ..i18n import set_language

                set_language(new_lang)
                self.owner.statusBar().showMessage(
                    "App language will fully apply after restarting Cyctitles", 6000
                )
            except Exception:  # noqa: BLE001
                pass
        new_theme = self.theme_combo2.currentData() or "auto"
        if getattr(self.cfg, "theme", "auto") != new_theme:
            self.cfg.theme = new_theme
            try:
                from ..ui.theme import apply_theme

                apply_theme(new_theme)
            except Exception:  # noqa: BLE001
                pass
        new_port = int(self.overlay_port_spin.value())
        if new_port != self.cfg.overlay_port:
            self.cfg.overlay_port = new_port
            if hasattr(self.owner, "restart_overlay_server"):
                self.owner.restart_overlay_server()
        self._changed()

    def _on_hotkey_changed(self) -> None:
        if self._loading:
            return
        self.owner.apply_hotkey(self.hotkey_edit.text())

    def _test_voice(self) -> None:
        from .. import tts

        tts.speak("This is a Cyctitles voice test.", self.cfg.tts_rate, self.cfg.tts_volume)
