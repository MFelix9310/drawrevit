"""Panel for loading Revit families (.rfa) into a project."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class FamiliesPanel(QWidget):
    """Panel for selecting and sending .rfa families to Revit."""

    send_requested = Signal(list)  # list of file paths

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlPanel")
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Cargar Familias")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#007acc;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # --- Description ---
        desc = QLabel("Selecciona archivos .rfa para cargar en el proyecto de Revit.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#999; font-size:12px;")
        root.addWidget(desc)

        # --- Add files buttons ---
        btn_row = QHBoxLayout()

        self._btn_add = QPushButton("Agregar Archivos")
        self._btn_add.setObjectName("AddButton")
        btn_row.addWidget(self._btn_add)

        self._btn_add_folder = QPushButton("Agregar Carpeta")
        self._btn_add_folder.setObjectName("AddFolderButton")
        btn_row.addWidget(self._btn_add_folder)

        root.addLayout(btn_row)

        # --- File list ---
        list_header = QLabel("Familias seleccionadas:")
        list_header.setObjectName("SectionHeader")
        root.addWidget(list_header)

        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self._file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._file_list, stretch=1)

        # --- Count label ---
        self._count_label = QLabel("0 familias seleccionadas")
        self._count_label.setStyleSheet("color:#999; font-size:12px;")
        root.addWidget(self._count_label)

        # --- Remove button ---
        self._btn_remove = QPushButton("Quitar Seleccionados")
        self._btn_remove.setObjectName("ResetButton")
        root.addWidget(self._btn_remove)

        # --- Send button ---
        self._btn_send = QPushButton("Cargar en Revit")
        self._btn_send.setObjectName("SendButton")
        root.addWidget(self._btn_send)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(20)
        root.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

    def _connect_signals(self):
        self._btn_add.clicked.connect(self._on_add_files)
        self._btn_add_folder.clicked.connect(self._on_add_folder)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_send.clicked.connect(self._on_send)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar Familias",
            "",
            "Revit Families (*.rfa);;All Files (*)",
        )
        for f in files:
            self._add_file(f)
        self._update_count()

    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar Carpeta")
        if folder:
            for rfa in Path(folder).rglob("*.rfa"):
                self._add_file(str(rfa))
        self._update_count()

    def _on_remove(self):
        for item in self._file_list.selectedItems():
            self._file_list.takeItem(self._file_list.row(item))
        self._update_count()

    def _on_send(self):
        paths = self.get_file_paths()
        if not paths:
            self.set_status("No hay familias seleccionadas.", False)
            return
        self.send_requested.emit(paths)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_file(self, path: str):
        # Avoid duplicates
        for i in range(self._file_list.count()):
            if self._file_list.item(i).data(Qt.UserRole) == path:
                return
        item = QListWidgetItem(Path(path).name)
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self._file_list.addItem(item)

    def _update_count(self):
        n = self._file_list.count()
        self._count_label.setText(f"{n} familia{'s' if n != 1 else ''} seleccionada{'s' if n != 1 else ''}")

    def get_file_paths(self) -> list[str]:
        return [
            self._file_list.item(i).data(Qt.UserRole)
            for i in range(self._file_list.count())
        ]

    def set_sending(self, active: bool):
        self._progress.setVisible(active)
        self._btn_send.setEnabled(not active)
        if active:
            self._status_label.setText("")

    def set_status(self, text: str, success: bool):
        color = "#4ec94e" if success else "#ef5350"
        self._status_label.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_label.setText(text)
