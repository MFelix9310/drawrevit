"""Left control panel: sliders, spacing inputs, action buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Defaults
DEFAULT_NUM_X = 4
DEFAULT_NUM_Y = 3
DEFAULT_SPACING = 6.0


class ControlPanel(QWidget):
    """Left-hand panel with all controls."""

    # Signals
    grids_changed = Signal()  # emitted whenever any value changes
    send_requested = Signal()
    reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlPanel")
        self.setFixedWidth(360)
        self._spacing_inputs_x: list[QDoubleSpinBox] = []
        self._spacing_inputs_y: list[QDoubleSpinBox] = []
        self._setup_ui()
        self._connect_signals()
        # initial population
        self._rebuild_spacing_fields()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- Title ---
        title = QLabel("Grid Generator")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#007acc;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # --- Section 1: Number of grids ---
        root.addWidget(self._section_header("Numero de Grids"))

        # Slider X
        self._label_x = QLabel(f"Grids X: {DEFAULT_NUM_X}")
        self._label_x.setObjectName("SliderValue")
        root.addWidget(self._label_x)

        self._slider_x = QSlider(Qt.Horizontal)
        self._slider_x.setRange(1, 20)
        self._slider_x.setValue(DEFAULT_NUM_X)
        root.addWidget(self._slider_x)

        # Slider Y
        self._label_y = QLabel(f"Grids Y: {DEFAULT_NUM_Y}")
        self._label_y.setObjectName("SliderValue")
        root.addWidget(self._label_y)

        self._slider_y = QSlider(Qt.Horizontal)
        self._slider_y.setRange(1, 20)
        self._slider_y.setValue(DEFAULT_NUM_Y)
        root.addWidget(self._slider_y)

        # --- Section 2: Spacings ---
        root.addWidget(self._section_header("Luces (espaciado)"))

        # Scroll area for spacing inputs
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._spacing_container = QWidget()
        self._spacing_layout = QGridLayout(self._spacing_container)
        self._spacing_layout.setContentsMargins(0, 0, 0, 0)
        self._spacing_layout.setSpacing(6)
        self._scroll.setWidget(self._spacing_container)
        root.addWidget(self._scroll, stretch=1)

        # --- Section 3: Actions ---
        root.addWidget(self._section_header("Acciones"))

        self._btn_send = QPushButton("Enviar a Revit")
        self._btn_send.setObjectName("SendButton")
        root.addWidget(self._btn_send)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        self._progress.setFixedHeight(20)
        root.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setObjectName("ResetButton")
        root.addWidget(self._btn_reset)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _section_header(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SectionHeader")
        return lbl

    def _make_spinbox(self, default: float = DEFAULT_SPACING) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(0.5, 50.0)
        sb.setSingleStep(0.25)
        sb.setDecimals(2)
        sb.setValue(default)
        sb.setSuffix(" m")
        sb.valueChanged.connect(self._on_spacing_changed)
        return sb

    # ------------------------------------------------------------------
    # Dynamic spacing fields
    # ------------------------------------------------------------------

    def _rebuild_spacing_fields(self):
        """Regenerate spacing input fields based on current slider values."""
        # Clear existing
        while self._spacing_layout.count():
            item = self._spacing_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        num_x = self._slider_x.value()
        num_y = self._slider_y.value()

        old_vals_x = [sb.value() for sb in self._spacing_inputs_x]
        old_vals_y = [sb.value() for sb in self._spacing_inputs_y]
        self._spacing_inputs_x.clear()
        self._spacing_inputs_y.clear()

        row = 0

        # Headers
        hdr_x = QLabel("Luces X")
        hdr_x.setStyleSheet("color:#4fc3f7; font-weight:bold;")
        hdr_y = QLabel("Luces Y")
        hdr_y.setStyleSheet("color:#ef9a9a; font-weight:bold;")
        self._spacing_layout.addWidget(hdr_x, row, 0)
        self._spacing_layout.addWidget(hdr_y, row, 1)
        row += 1

        max_fields = max(num_x - 1, num_y - 1, 0)

        for i in range(max_fields):
            # X column
            if i < num_x - 1:
                lbl = QLabel(f"X{i + 1}:")
                lbl.setFixedWidth(30)
                default_val = old_vals_x[i] if i < len(old_vals_x) else DEFAULT_SPACING
                sb = self._make_spinbox(default_val)
                h = QHBoxLayout()
                h.setContentsMargins(0, 0, 4, 0)
                h.addWidget(lbl)
                h.addWidget(sb)
                container = QWidget()
                container.setLayout(h)
                self._spacing_layout.addWidget(container, row, 0)
                self._spacing_inputs_x.append(sb)
            else:
                self._spacing_layout.addWidget(QLabel(""), row, 0)

            # Y column
            if i < num_y - 1:
                lbl = QLabel(f"Y{i + 1}:")
                lbl.setFixedWidth(30)
                default_val = old_vals_y[i] if i < len(old_vals_y) else DEFAULT_SPACING
                sb = self._make_spinbox(default_val)
                h = QHBoxLayout()
                h.setContentsMargins(4, 0, 0, 0)
                h.addWidget(lbl)
                h.addWidget(sb)
                container = QWidget()
                container.setLayout(h)
                self._spacing_layout.addWidget(container, row, 1)
                self._spacing_inputs_y.append(sb)
            else:
                self._spacing_layout.addWidget(QLabel(""), row, 1)

            row += 1

        # Spacer at bottom
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._spacing_layout.addWidget(spacer, row, 0, 1, 2)

        self.grids_changed.emit()

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self._slider_x.valueChanged.connect(self._on_slider_x)
        self._slider_y.valueChanged.connect(self._on_slider_y)
        self._btn_send.clicked.connect(self.send_requested)
        self._btn_reset.clicked.connect(self._do_reset)

    def _on_slider_x(self, val: int):
        self._label_x.setText(f"Grids X: {val}")
        self._rebuild_spacing_fields()

    def _on_slider_y(self, val: int):
        self._label_y.setText(f"Grids Y: {val}")
        self._rebuild_spacing_fields()

    def _on_spacing_changed(self):
        self.grids_changed.emit()

    def _do_reset(self):
        self._slider_x.setValue(DEFAULT_NUM_X)
        self._slider_y.setValue(DEFAULT_NUM_Y)
        # _rebuild_spacing_fields is called by slider valueChanged
        self.reset_requested.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def num_x(self) -> int:
        return self._slider_x.value()

    @property
    def num_y(self) -> int:
        return self._slider_y.value()

    @property
    def spacings_x(self) -> list[float]:
        return [sb.value() for sb in self._spacing_inputs_x]

    @property
    def spacings_y(self) -> list[float]:
        return [sb.value() for sb in self._spacing_inputs_y]

    def set_sending(self, active: bool):
        """Toggle progress bar and disable button while sending."""
        self._progress.setVisible(active)
        self._btn_send.setEnabled(not active)
        if active:
            self._status_label.setText("")

    def set_status(self, text: str, success: bool):
        color = "#4ec94e" if success else "#ef5350"
        self._status_label.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_label.setText(text)
