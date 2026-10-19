"""Model management hub: storage folder, custom folders, downloaded models,
and a searchable catalog of every model that can be downloaded."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import WHISPER_MODELS, Config, resolved_models_dir
from ..models import (
    CUSTOM_REPO,
    LANGUAGE_NAMES,
    TRANSLATION_MODELS,
    ModelInfo,
    custom_translation_info,
    custom_whisper_info,
    delete_model,
    directory_size,
    human_size,
    is_translation_downloaded,
    missing_keys_for_path,
    move_models_dir,
    translation_model_info,
    whisper_model_info,
    find_translation_path,
)
from ..i18n import tr
from .download_dialog import run_download

# All catalog entries (whisper + translation), as ModelInfo, given a models dir.
def catalog_infos(models_dir: Path) -> list[ModelInfo]:
    infos = [whisper_model_info(name, models_dir) for name in WHISPER_MODELS if name != "auto"]
    infos += [translation_model_info(spec.key, models_dir) for spec in TRANSLATION_MODELS]
    return infos


class ModelsDialog(QDialog):
    """Manage everything about models in one place."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = config
        self.models_dir = resolved_models_dir(config)
        self.changed = False
        self.setWindowTitle(tr("models_title"))
        self.setMinimumSize(760, 560)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(self._build_storage_section())
        layout.addWidget(self._build_custom_section())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_downloaded_tab(), tr("models_tab_downloaded"))
        self.tabs.addTab(self._build_catalog_tab(), tr("models_tab_catalog"))
        layout.addWidget(self.tabs, 1)

        self.total_label = QLabel()
        self.total_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.total_label)

        buttons = QDialogButtonBox()
        close = buttons.addButton(tr("btn_close"), QDialogButtonBox.ButtonRole.RejectRole)
        close.setDefault(True)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh()

    # -- storage / custom ----------------------------------------------------
    def _h_line(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _build_storage_section(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        row = QHBoxLayout()
        row.addWidget(QLabel(f"<b>{tr('models_folder')}</b>"))
        row.addStretch(1)
        open_btn = QPushButton(tr("models_open_folder"))
        open_btn.clicked.connect(self._open_folder)
        row.addWidget(open_btn)
        change = QPushButton(tr("models_change_folder"))
        change.clicked.connect(self._change_folder)
        row.addWidget(change)
        v.addLayout(row)

        self.folder_label = QLabel()
        self.folder_label.setWordWrap(True)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder_label.setStyleSheet(
            "color: gray; font-size: 11px; font-family: Consolas, monospace;"
        )
        v.addWidget(self.folder_label)
        return box

    def _build_custom_section(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        title = QLabel(f"<b>{tr('models_custom')}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setWordWrap(True)
        v.addWidget(title)

        self.whisper_custom_label = QLabel()
        self.whisper_custom_label.setWordWrap(True)
        self.whisper_custom_label.setStyleSheet("color: gray; font-size: 11px;")
        v.addWidget(
            self._custom_row(self.whisper_custom_label, self._choose_whisper, self._clear_whisper)
        )

        self.mt_custom_label = QLabel()
        self.mt_custom_label.setWordWrap(True)
        self.mt_custom_label.setStyleSheet("color: gray; font-size: 11px;")
        v.addWidget(self._custom_row(self.mt_custom_label, self._choose_mt, self._clear_mt))
        return box

    def _custom_row(self, label: QLabel, choose, clear) -> QWidget:  # noqa: ANN001
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(label, 1)
        choose_btn = QPushButton(tr("btn_choose"))
        choose_btn.clicked.connect(choose)
        h.addWidget(choose_btn)
        clear_btn = QPushButton(tr("btn_clear"))
        clear_btn.clicked.connect(clear)
        h.addWidget(clear_btn)
        return row

    def _open_folder(self) -> None:
        from PySide6.QtCore import QUrl, QDesktopServices

        self.models_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.models_dir)))

    # -- downloaded tab ------------------------------------------------------
    def _build_downloaded_tab(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 4, 4, 4)

        row = QHBoxLayout()
        note = QLabel(tr("models_downloaded_note"))
        note.setStyleSheet("color: gray; font-size: 11px;")
        note.setWordWrap(True)
        row.addWidget(note, 1)
        repair = QPushButton(tr("models_repair"))
        repair.setToolTip(tr("models_repair_tip"))
        repair.clicked.connect(self._repair_all)
        row.addWidget(repair)
        v.addLayout(row)

        self.downloaded_table = QTableWidget(0, 4)
        self.downloaded_table.setHorizontalHeaderLabels(
            [tr("col_model"), tr("col_type"), tr("col_size"), tr("col_action")]
        )
        self.downloaded_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.downloaded_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.downloaded_table.verticalHeader().setVisible(False)
        self.downloaded_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.downloaded_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.downloaded_table.setAlternatingRowColors(True)
        v.addWidget(self.downloaded_table, 1)
        return box

    # -- catalog tab ---------------------------------------------------------
    def _build_catalog_tab(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 4, 4, 4)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("models_search_placeholder"))
        self.search_edit.textChanged.connect(self._refresh_catalog)
        filters.addWidget(self.search_edit, 2)

        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("filter_all"), "all")
        self.type_combo.addItem(tr("filter_whisper"), "whisper")
        self.type_combo.addItem(tr("filter_translation"), "translation")
        self.type_combo.currentIndexChanged.connect(self._refresh_catalog)
        filters.addWidget(self.type_combo)

        self.lang_combo = QComboBox()
        self.lang_combo.addItem(tr("filter_any_lang"), "")
        for code in sorted(LANGUAGE_NAMES):
            self.lang_combo.addItem(LANGUAGE_NAMES[code], code)
        self.lang_combo.currentIndexChanged.connect(self._refresh_catalog)
        filters.addWidget(self.lang_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem(tr("sort_name"), "name")
        self.sort_combo.addItem(tr("sort_size"), "size")
        self.sort_combo.addItem(tr("sort_downloaded"), "downloaded")
        self.sort_combo.currentIndexChanged.connect(self._refresh_catalog)
        filters.addWidget(self.sort_combo)
        v.addLayout(filters)

        self.catalog_table = QTableWidget(0, 5)
        self.catalog_table.setHorizontalHeaderLabels(
            [
                tr("col_model"),
                tr("col_languages"),
                tr("col_size"),
                tr("col_status"),
                tr("col_action"),
            ]
        )
        self.catalog_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.catalog_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.catalog_table.verticalHeader().setVisible(False)
        self.catalog_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.catalog_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.catalog_table.setAlternatingRowColors(True)
        v.addWidget(self.catalog_table, 1)
        return box

    # -- custom pickers ------------------------------------------------------
    def _choose_whisper(self) -> None:
        self._choose_custom("whisper_model_path")

    def _choose_mt(self) -> None:
        self._choose_custom("translation_model_path")

    def _clear_whisper(self) -> None:
        self.cfg.whisper_model_path = ""
        self.changed = True
        self._refresh()

    def _clear_mt(self) -> None:
        self.cfg.translation_model_path = ""
        self.changed = True
        self._refresh()

    def _choose_custom(self, attr: str) -> None:
        current = getattr(self.cfg, attr, "")
        start = current or str(self.models_dir)
        chosen = QFileDialog.getExistingDirectory(self, tr("models_choose_folder"), start)
        if not chosen:
            return
        setattr(self.cfg, attr, chosen)
        self.changed = True
        self._refresh()

    def _change_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, tr("models_choose_folder"), str(self.models_dir)
        )
        if not chosen:
            return
        new = Path(chosen)
        old = self.models_dir
        if new.resolve() == old.resolve():
            return
        if old.exists():
            try:
                has_content = any(old.iterdir())
            except OSError:
                has_content = False
            if has_content:
                move = QMessageBox.question(
                    self,
                    tr("models_move_title"),
                    tr("models_move_body", old=old, new=new),
                )
                if move == QMessageBox.StandardButton.Yes:
                    moved = move_models_dir(old, new)
                    QMessageBox.information(
                        self, "Cyctitles", tr("models_moved_done", n=moved)
                    )
        self.cfg.models_dir = str(new)
        self.models_dir = new
        self.changed = True
        self._refresh()

    # -- refresh -------------------------------------------------------------
    def _refresh(self) -> None:
        self.models_dir = resolved_models_dir(self.cfg)
        self.folder_label.setText(str(self.models_dir))
        self._refresh_custom_labels()
        self._refresh_downloaded()
        self._refresh_catalog()
        self._refresh_total()

    def _refresh_total(self) -> None:
        total = directory_size(self.models_dir)
        self.total_label.setText(tr("models_total", size=human_size(total)))

    def _refresh_custom_labels(self) -> None:
        self.whisper_custom_label.setText(
            self._custom_text("whisper_model_path", custom_whisper_info)
        )
        self.mt_custom_label.setText(
            self._custom_text("translation_model_path", custom_translation_info)
        )

    def _custom_text(self, attr: str, info_fn) -> str:  # noqa: ANN001
        value = getattr(self.cfg, attr, "")
        kind = "Whisper" if attr == "whisper_model_path" else "Translation"
        if not value:
            return tr("models_custom_default", kind=kind)
        info = info_fn(value)
        if info.downloaded:
            return tr("models_custom_valid", kind=kind, path=value)
        missing = (
            "no model.bin found" if attr == "whisper_model_path" else "required files missing"
        )
        return tr("models_custom_invalid", kind=kind, path=value, missing=missing)

    def _all_infos(self) -> list[ModelInfo]:
        infos = [
            whisper_model_info(name, self.models_dir)
            for name in WHISPER_MODELS
            if name != "auto"
        ]
        infos += [translation_model_info(spec.key, self.models_dir) for spec in TRANSLATION_MODELS]
        return infos

    def _refresh_downloaded(self) -> None:
        rows = [i for i in self._all_infos() if i.downloaded]
        self.downloaded_table.setRowCount(len(rows))
        for r, info in enumerate(rows):
            size = human_size(directory_size(info.directory))
            self.downloaded_table.setItem(r, 0, QTableWidgetItem(info.label))
            self.downloaded_table.setItem(r, 1, QTableWidgetItem(info.kind.title()))
            self.downloaded_table.setItem(r, 2, QTableWidgetItem(size))
            self.downloaded_table.setCellWidget(r, 3, self._action_button(info, small=True))

    def _refresh_catalog(self) -> None:
        needle = self.search_edit.text().strip().lower()
        kind_filter = self.type_combo.currentData()
        lang_filter = self.lang_combo.currentData()
        sort = self.sort_combo.currentData()

        entries = catalog_infos(self.models_dir)
        filtered: list[ModelInfo] = []
        for info in entries:
            if kind_filter != "all" and info.kind != kind_filter:
                continue
            if lang_filter:
                if info.kind == "translation":
                    spec_langs = {info.key.split("-")[-1], info.key.split("-")[-2]}
                    if lang_filter not in spec_langs:
                        continue
                else:
                    continue
            if needle:
                haystack = f"{info.label} {info.repo_id} {info.key}".lower()
                if needle not in haystack:
                    continue
            filtered.append(info)

        if sort == "size":
            filtered.sort(key=lambda i: i.size_bytes, reverse=True)
        elif sort == "downloaded":
            filtered.sort(key=lambda i: (not i.downloaded, i.label))
        else:
            filtered.sort(key=lambda i: i.label)

        self.catalog_table.setRowCount(len(filtered))
        for r, info in enumerate(filtered):
            langs = ""
            if info.kind == "translation":
                parts = info.key.split("-")  # quickmt-src-tgt
                src, tgt = parts[-2], parts[-1]
                langs = f"{LANGUAGE_NAMES.get(src, src)} → {LANGUAGE_NAMES.get(tgt, tgt)}"
            else:
                langs = tr("col_speech")
            status = tr("status_downloaded") if info.downloaded else tr("status_not_downloaded")
            self.catalog_table.setItem(r, 0, QTableWidgetItem(info.label))
            self.catalog_table.setItem(r, 1, QTableWidgetItem(langs))
            self.catalog_table.setItem(r, 2, QTableWidgetItem(info.size_text))
            self.catalog_table.setItem(r, 3, QTableWidgetItem(status))
            self.catalog_table.setCellWidget(r, 4, self._action_button(info))

    def _action_button(self, info: ModelInfo, small: bool = False) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(4, 2, 4, 2)
        if info.downloaded:
            btn = QPushButton(tr("btn_delete"))
            btn.clicked.connect(lambda _=False, i=info: self._on_delete(i))
        else:
            btn = QPushButton(tr("btn_download"))
            btn.clicked.connect(lambda _=False, i=info: self._on_download(i))
        h.addWidget(btn)
        if small and info.kind == "translation" and info.repo_id != CUSTOM_REPO:
            verify = QPushButton(tr("btn_repair"))
            verify.setToolTip(tr("models_repair_tip"))
            verify.clicked.connect(lambda _=False, i=info: self._on_repair(i))
            h.addWidget(verify)
        return wrap

    def _on_download(self, info: ModelInfo) -> None:
        ok, error = run_download([info], self.models_dir, self)
        if not ok:
            QMessageBox.warning(self, "Cyctitles", tr("download_failed", label=info.label, err=error))
        self._refresh()

    def _on_delete(self, info: ModelInfo) -> None:
        if (
            QMessageBox.question(
                self,
                tr("models_delete_title"),
                tr("models_delete_body", label=info.label, size=human_size(directory_size(info.directory))),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        delete_model(info)
        self._refresh()

    def _on_repair(self, info: ModelInfo) -> None:
        ok, error = run_download([info], self.models_dir, self, force=True)
        if ok:
            QMessageBox.information(self, "Cyctitles", tr("models_repair_done", label=info.label))
        else:
            QMessageBox.warning(self, "Cyctitles", tr("download_failed", label=info.label, err=error))
        self._refresh()

    def _repair_all(self) -> None:
        """Re-download anything the current setup still needs (e.g. a pivot path)."""
        src = self.cfg.src_lang
        tgt = self.cfg.tgt_lang
        path = find_translation_path(src, tgt)
        needed = missing_keys_for_path(path, self.models_dir)
        infos = [translation_model_info(k, self.models_dir) for k in needed]
        whisper_name = self.cfg.whisper_model
        if whisper_name and whisper_name != "auto":
            w = whisper_model_info(whisper_name, self.models_dir)
            if not w.downloaded:
                infos.append(w)
        if not infos:
            QMessageBox.information(
                self, "Cyctitles", tr("models_repair_nothing", pair=f"{src} → {tgt}")
            )
            return
        labels = ", ".join(i.label for i in infos)
        if (
            QMessageBox.question(self, tr("models_repair"), tr("models_repair_confirm", labels=labels))
            != QMessageBox.StandardButton.Yes
        ):
            return
        ok, error = run_download(infos, self.models_dir, self, force=True)
        if not ok:
            QMessageBox.warning(self, "Cyctitles", tr("download_failed", label=labels, err=error))
        self._refresh()
