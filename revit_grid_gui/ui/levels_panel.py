"""Panel for managing Revit levels: add, edit, delete."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


DEFAULT_LEVELS = [
    ("Cimentacion", -1.50),
    ("Nivel 1", 0.00),
    ("Nivel 2", 3.20),
    ("Nivel 3", 6.40),
]


class LevelsPanel(QWidget):
    """Panel for configuring and sending levels to Revit."""

    send_requested = Signal(list, bool)  # (levels, replace_existing)
    fetch_requested = Signal()          # request current levels from Revit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlPanel")
        self._setup_ui()
        self._connect_signals()
        self._load_defaults()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # --- Title ---
        title = QLabel("Niveles")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#007acc;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # --- Fetch from Revit ---
        self._btn_fetch = QPushButton("Obtener Niveles de Revit")
        self._btn_fetch.setObjectName("AddButton")
        root.addWidget(self._btn_fetch)

        # --- Table ---
        table_header = QLabel("Niveles:")
        table_header.setObjectName("SectionHeader")
        root.addWidget(table_header)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Nombre", "Elevacion (m)"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self._table.setColumnWidth(1, 120)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.ExtendedSelection)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self._table, stretch=1)

        # --- Add row ---
        add_row_layout = QHBoxLayout()

        self._input_name = QLineEdit()
        self._input_name.setPlaceholderText("Nombre del nivel")
        self._input_name.setMinimumHeight(32)
        add_row_layout.addWidget(self._input_name, stretch=1)

        self._input_elev = QDoubleSpinBox()
        self._input_elev.setRange(-100.0, 1000.0)
        self._input_elev.setSingleStep(0.10)
        self._input_elev.setDecimals(2)
        self._input_elev.setValue(0.0)
        self._input_elev.setSuffix(" m")
        self._input_elev.setMinimumHeight(32)
        add_row_layout.addWidget(self._input_elev)

        self._btn_add = QPushButton("+")
        self._btn_add.setObjectName("AddButton")
        self._btn_add.setFixedSize(36, 36)
        add_row_layout.addWidget(self._btn_add)

        root.addLayout(add_row_layout)

        # --- Action buttons row ---
        btn_row = QHBoxLayout()

        self._btn_remove = QPushButton("Quitar")
        self._btn_remove.setObjectName("ResetButton")
        btn_row.addWidget(self._btn_remove)

        self._btn_sort = QPushButton("Ordenar")
        self._btn_sort.setObjectName("AddFolderButton")
        btn_row.addWidget(self._btn_sort)

        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setObjectName("ResetButton")
        btn_row.addWidget(self._btn_reset)

        root.addLayout(btn_row)

        # --- Replace checkbox ---
        self._chk_replace = QCheckBox("Reemplazar niveles existentes (borrar todos y crear nuevos)")
        self._chk_replace.setChecked(True)
        self._chk_replace.setStyleSheet("color:#ffd54f; font-size:12px; padding:4px 0;")
        root.addWidget(self._chk_replace)

        # --- Send ---
        self._btn_send = QPushButton("Enviar Niveles a Revit")
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
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_sort.clicked.connect(self._on_sort)
        self._btn_reset.clicked.connect(self._load_defaults)
        self._btn_send.clicked.connect(self._on_send)
        self._btn_fetch.clicked.connect(self.fetch_requested)
        self._input_name.returnPressed.connect(self._on_add)

    # ------------------------------------------------------------------
    # Table operations
    # ------------------------------------------------------------------

    def _add_level_row(self, name: str, elevation: float):
        row = self._table.rowCount()
        self._table.insertRow(row)

        name_item = QTableWidgetItem(name)
        self._table.setItem(row, 0, name_item)

        elev_spin = QDoubleSpinBox()
        elev_spin.setRange(-100.0, 1000.0)
        elev_spin.setSingleStep(0.10)
        elev_spin.setDecimals(2)
        elev_spin.setValue(elevation)
        elev_spin.setSuffix(" m")
        self._table.setCellWidget(row, 1, elev_spin)

    def _on_add(self):
        name = self._input_name.text().strip()
        if not name:
            return
        elev = self._input_elev.value()
        self._add_level_row(name, elev)
        self._input_name.clear()
        self._input_elev.setValue(elev + 3.20)  # suggest next elevation
        self._input_name.setFocus()

    def _on_remove(self):
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        for row in rows:
            self._table.removeRow(row)

    def _on_sort(self):
        """Sort table rows by elevation ascending."""
        levels = self._get_levels()
        levels.sort(key=lambda lv: lv["elevation"])
        self._table.setRowCount(0)
        for lv in levels:
            self._add_level_row(lv["name"], lv["elevation"])

    def _on_send(self):
        levels = self._get_levels()
        if not levels:
            self.set_status("No hay niveles definidos.", False)
            return
        self.send_requested.emit(levels, self._chk_replace.isChecked())

    def _load_defaults(self):
        self._table.setRowCount(0)
        for name, elev in DEFAULT_LEVELS:
            self._add_level_row(name, elev)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _get_levels(self) -> list[dict]:
        levels = []
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            elev_widget = self._table.cellWidget(row, 1)
            if name_item and elev_widget:
                levels.append({
                    "name": name_item.text(),
                    "elevation": elev_widget.value(),
                })
        return levels

    def populate_from_revit(self, levels: list[dict]):
        """Fill the table with levels fetched from Revit."""
        self._table.setRowCount(0)
        for lv in levels:
            self._add_level_row(lv["name"], lv["elevation"])

    def set_sending(self, active: bool):
        self._progress.setVisible(active)
        self._btn_send.setEnabled(not active)
        self._btn_fetch.setEnabled(not active)
        if active:
            self._status_label.setText("")

    def set_status(self, text: str, success: bool):
        color = "#4ec94e" if success else "#ef5350"
        self._status_label.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_label.setText(text)
