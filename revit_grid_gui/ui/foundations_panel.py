"""Panel for creating structural foundations (with pedestal) at grid intersections."""

from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPolygonF
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# ──────────────────────────────────────────────────────────────
# Diagram widgets: Plan, Section, 3D isometric
# ──────────────────────────────────────────────────────────────

_BG = QColor("#1e1e1e")
_FOOTING_COLOR = QColor("#5a7fa5")
_FOOTING_EDGE = QColor("#7aafdf")
_PEDESTAL_COLOR = QColor("#a57f5a")
_PEDESTAL_EDGE = QColor("#dfaf7a")
_DIM_COLOR = QColor("#888888")
_GRID_DOT = QColor("#ff5555")
_LABEL_FONT = None


def _get_label_font():
    """Lazy-init label font to avoid QFont before QApplication exists."""
    global _LABEL_FONT
    if _LABEL_FONT is None:
        _LABEL_FONT = QFont("Segoe UI", 7)
    return _LABEL_FONT


class _DiagramBase(QWidget):
    """Base for footing diagram drawings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(105, 95)
        self.setMaximumHeight(110)
        # Foundation dims (mm) — updated externally
        self.f_w = 1500.0
        self.f_l = 1500.0
        self.f_t = 400.0
        # Pedestal dims (mm)
        self.p_w = 400.0
        self.p_l = 400.0
        self.p_h = 600.0
        # Type: "central", "esquinera", "lindero"
        self.ftype = "central"

    def update_dims(self, f_w, f_l, f_t, p_w, p_l, p_h):
        self.f_w = f_w
        self.f_l = f_l
        self.f_t = f_t
        self.p_w = p_w
        self.p_l = p_l
        self.p_h = p_h
        self.update()


class PlanDiagram(_DiagramBase):
    """Top-down plan view of foundation + pedestal."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), _BG)

        w, h = self.width(), self.height()
        margin = 12
        draw_w = w - 2 * margin
        draw_h = h - 2 * margin

        # Scale to fit
        max_dim = max(self.f_w, self.f_l)
        scale = min(draw_w, draw_h) / max_dim if max_dim > 0 else 1.0

        fw = self.f_w * scale
        fl = self.f_l * scale
        pw = self.p_w * scale
        pl = self.p_l * scale

        # Center origin
        cx = w / 2.0
        cy = h / 2.0

        # Foundation rect (centered)
        fx = cx - fw / 2.0
        fy = cy - fl / 2.0
        p.setPen(QPen(_FOOTING_EDGE, 1.5))
        p.setBrush(QBrush(_FOOTING_COLOR))
        p.drawRect(QRectF(fx, fy, fw, fl))

        # Pedestal position depends on type
        if self.ftype == "central":
            px = cx - pw / 2.0
            py = cy - pl / 2.0
        elif self.ftype == "esquinera":
            px = fx
            py = fy
        else:  # lindero
            px = cx - pw / 2.0
            py = fy

        p.setPen(QPen(_PEDESTAL_EDGE, 1.5))
        p.setBrush(QBrush(_PEDESTAL_COLOR))
        p.drawRect(QRectF(px, py, pw, pl))

        # Grid intersection dot
        if self.ftype == "central":
            dot_x, dot_y = cx, cy
        elif self.ftype == "esquinera":
            dot_x, dot_y = fx, fy
        else:
            dot_x, dot_y = cx, fy

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_GRID_DOT))
        p.drawEllipse(QPointF(dot_x, dot_y), 3, 3)

        # Label
        p.setPen(QPen(_DIM_COLOR))
        p.setFont(_get_label_font())
        p.drawText(QRectF(0, h - 14, w, 14), Qt.AlignCenter, "PLANTA")
        p.end()


class SectionDiagram(_DiagramBase):
    """Cross-section view (side) of foundation + pedestal."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), _BG)

        w, h = self.width(), self.height()
        margin = 12
        draw_w = w - 2 * margin
        draw_h = h - 2 * margin - 14  # leave room for label

        total_h = self.f_t + self.p_h
        max_w = max(self.f_w, self.p_w)
        scale = min(draw_w / max_w, draw_h / total_h) if max_w > 0 and total_h > 0 else 1.0

        fw = self.f_w * scale
        ft = self.f_t * scale
        pw = self.p_w * scale
        ph = self.p_h * scale

        cx = w / 2.0
        base_y = margin + draw_h  # bottom of drawing area

        # Foundation (bottom block)
        fx = cx - fw / 2.0
        fy = base_y - ft
        p.setPen(QPen(_FOOTING_EDGE, 1.5))
        p.setBrush(QBrush(_FOOTING_COLOR))
        p.drawRect(QRectF(fx, fy, fw, ft))

        # Pedestal (top block)
        if self.ftype == "central":
            pedx = cx - pw / 2.0
        elif self.ftype == "esquinera":
            pedx = fx
        else:  # lindero
            pedx = cx - pw / 2.0

        pedy = fy - ph
        p.setPen(QPen(_PEDESTAL_EDGE, 1.5))
        p.setBrush(QBrush(_PEDESTAL_COLOR))
        p.drawRect(QRectF(pedx, pedy, pw, ph))

        # Dimension lines
        p.setPen(QPen(_DIM_COLOR, 0.5, Qt.DashLine))
        p.setFont(_get_label_font())

        # Foundation width dimension
        dim_y = base_y + 2
        p.drawLine(QPointF(fx, dim_y), QPointF(fx + fw, dim_y))
        p.drawText(QRectF(fx, dim_y, fw, 12), Qt.AlignCenter, "%d" % int(self.f_w))

        # Height dimension (right side)
        dim_x = fx + fw + 3
        p.drawLine(QPointF(dim_x, fy), QPointF(dim_x, base_y))
        p.drawLine(QPointF(dim_x, pedy), QPointF(dim_x, fy))

        # Label
        p.setPen(QPen(_DIM_COLOR))
        p.setFont(_get_label_font())
        p.drawText(QRectF(0, h - 14, w, 14), Qt.AlignCenter, "SECCION")
        p.end()


class Iso3DDiagram(_DiagramBase):
    """Simple isometric 3D view of foundation + pedestal."""

    def _iso(self, x, y, z, cx, cy, scale):
        """Convert 3D coords to 2D isometric."""
        ix = (x - y) * math.cos(math.radians(30)) * scale
        iy = -(x + y) * math.sin(math.radians(30)) * scale - z * scale
        return QPointF(cx + ix, cy - iy)

    def _draw_box(self, p, cx, cy, scale, ox, oy, oz, bw, bl, bh, fill, edge):
        """Draw an isometric box."""
        # 8 corners
        corners = []
        for dz in [0, bh]:
            for dy in [0, bl]:
                for dx in [0, bw]:
                    corners.append(self._iso(ox + dx, oy + dy, oz + dz, cx, cy, scale))

        # Faces (only visible ones: top, front-right, front-left)
        # Top face: corners 4,5,7,6
        top = QPolygonF([corners[4], corners[5], corners[7], corners[6]])
        # Right face: corners 1,3,7,5
        right = QPolygonF([corners[1], corners[3], corners[7], corners[5]])
        # Front face: corners 2,3,7,6
        front = QPolygonF([corners[2], corners[3], corners[7], corners[6]])

        light = QColor(fill)
        light.setAlpha(220)
        dark = QColor(fill)
        dark.setRed(max(0, dark.red() - 30))
        dark.setGreen(max(0, dark.green() - 30))
        dark.setBlue(max(0, dark.blue() - 30))
        dark.setAlpha(220)

        pen = QPen(edge, 1.0)

        # Draw front face
        p.setPen(pen)
        p.setBrush(QBrush(dark))
        p.drawPolygon(front)

        # Draw right face
        p.setBrush(QBrush(fill))
        p.drawPolygon(right)

        # Draw top face
        p.setBrush(QBrush(light))
        p.drawPolygon(top)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), _BG)

        w, h = self.width(), self.height()
        cx = w / 2.0
        cy = h * 0.65

        total_h = self.f_t + self.p_h
        max_dim = max(self.f_w, self.f_l, total_h)
        scale = min(w, h) * 0.28 / max_dim if max_dim > 0 else 0.01

        # Normalize to mm for drawing
        fw = self.f_w
        fl = self.f_l
        ft = self.f_t
        pw_d = self.p_w
        pl_d = self.p_l
        ph_d = self.p_h

        # Foundation origin
        fox = -fw / 2.0
        foy = -fl / 2.0
        foz = 0.0

        # Pedestal origin depends on type
        if self.ftype == "central":
            pox = -pw_d / 2.0
            poy = -pl_d / 2.0
        elif self.ftype == "esquinera":
            pox = fox
            poy = foy
        else:  # lindero
            pox = -pw_d / 2.0
            poy = foy

        # Draw foundation first (bottom)
        self._draw_box(p, cx, cy, scale, fox, foy, foz, fw, fl, ft,
                        _FOOTING_COLOR, _FOOTING_EDGE)

        # Draw pedestal on top
        self._draw_box(p, cx, cy, scale, pox, poy, ft, pw_d, pl_d, ph_d,
                        _PEDESTAL_COLOR, _PEDESTAL_EDGE)

        # Label
        p.setPen(QPen(_DIM_COLOR))
        p.setFont(_get_label_font())
        p.drawText(QRectF(0, h - 14, w, 14), Qt.AlignCenter, "3D")
        p.end()


# ──────────────────────────────────────────────────────────────
# Foundation type tab (one per type: central, lindero, esquinera)
# ──────────────────────────────────────────────────────────────

class _FoundationTypeTab(QWidget):
    """Tab for configuring one type of foundation + pedestal with live diagrams."""

    config_changed = Signal()

    # Default dims per type: (f_w, f_l, f_t, p_w, p_l, p_h)
    DEFAULTS = {
        "central":   (1500, 1500, 400, 400, 400, 600),
        "esquinera": (1200, 1200, 400, 400, 400, 600),
        "lindero":   (1200, 1500, 400, 400, 400, 600),
    }

    def __init__(self, ftype: str, parent=None):
        super().__init__(parent)
        self._ftype = ftype
        defaults = self.DEFAULTS.get(ftype, self.DEFAULTS["central"])
        self._setup_ui(defaults)
        self._connect_value_signals()
        self._update_diagrams()

    def _setup_ui(self, defaults):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Diagrams row ---
        diagrams_row = QHBoxLayout()
        diagrams_row.setSpacing(4)

        self._plan = PlanDiagram()
        self._plan.ftype = self._ftype
        self._section = SectionDiagram()
        self._section.ftype = self._ftype
        self._iso3d = Iso3DDiagram()
        self._iso3d.ftype = self._ftype

        diagrams_row.addWidget(self._plan)
        diagrams_row.addWidget(self._section)
        diagrams_row.addWidget(self._iso3d)
        root.addLayout(diagrams_row)

        # --- Zapata config ---
        zapata_group = QGroupBox("Zapata")
        zapata_group.setStyleSheet("QGroupBox{font-weight:bold; color:#5a7fa5;}")
        zl = QVBoxLayout(zapata_group)
        zl.setSpacing(4)
        zl.setContentsMargins(8, 14, 8, 6)

        self._f_w = self._make_spin_row(zl, "Ancho (mm):", 200, 10000, defaults[0])
        self._f_l = self._make_spin_row(zl, "Largo (mm):", 200, 10000, defaults[1])
        self._f_t = self._make_spin_row(zl, "Espesor (mm):", 100, 3000, defaults[2])
        root.addWidget(zapata_group)

        # --- Pedestal config ---
        ped_group = QGroupBox("Pedestal")
        ped_group.setStyleSheet("QGroupBox{font-weight:bold; color:#a57f5a;}")
        pl = QVBoxLayout(ped_group)
        pl.setSpacing(4)
        pl.setContentsMargins(8, 14, 8, 6)

        self._p_w = self._make_spin_row(pl, "Ancho (mm):", 150, 5000, defaults[3])
        self._p_l = self._make_spin_row(pl, "Largo (mm):", 150, 5000, defaults[4])

        self._p_h = self._make_spin_row(pl, "Altura (mm):", 200, 5000, defaults[5])

        # Button to auto-calculate height to Nivel 0.0
        self._btn_auto_h = QPushButton("Altura al Nivel 0.0")
        self._btn_auto_h.setStyleSheet(
            "QPushButton {"
            "  background-color: #2a6e9e; color: white; border: none;"
            "  border-radius: 4px; padding: 6px; font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #3a8ebe; }"
        )
        self._btn_auto_h.setToolTip(
            "Calcula la altura para que el pedestal llegue al Nivel 0.0\n"
            "(profundidad cimentacion - espesor zapata)")
        self._btn_auto_h.clicked.connect(self._calc_height_to_nivel0)
        pl.addWidget(self._btn_auto_h)

        root.addWidget(ped_group)

        root.addStretch(1)

    @staticmethod
    def _make_spin_row(layout, label_text: str, lo: float, hi: float, default: float):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(95)
        row.addWidget(lbl)
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(default)
        spin.setSingleStep(50.0)
        spin.setDecimals(0)
        row.addWidget(spin)
        layout.addLayout(row)
        return spin

    def _connect_value_signals(self):
        for spin in [self._f_w, self._f_l, self._f_t, self._p_w, self._p_l, self._p_h]:
            spin.valueChanged.connect(self._update_diagrams)
            spin.valueChanged.connect(lambda _: self.config_changed.emit())

    def _calc_height_to_nivel0(self):
        """Calculate pedestal height so it reaches Nivel 0.0.
        height = abs(nivel_0 - cimentacion) - footing_thickness
        Queries the Revit API for level elevations (returned in meters)."""
        import requests
        thickness_mm = self._f_t.value()
        try:
            resp = requests.get("http://localhost:48884/grid-api/get_levels/", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                levels = data.get("levels", [])
                if not levels:
                    return
                # Cimentacion = lowest level
                levels_sorted = sorted(levels, key=lambda lv: lv.get("elevation", 0))
                cimentacion = levels_sorted[0]
                # Nivel 0 = level closest to elevation 0.0
                nivel_0 = min(levels, key=lambda lv: abs(lv.get("elevation", 999)))
                # Elevations are in METERS from the API
                cim_elev_mm = cimentacion.get("elevation", 0) * 1000.0
                n0_elev_mm = nivel_0.get("elevation", 0) * 1000.0
                depth_mm = abs(n0_elev_mm - cim_elev_mm)
                ped_height = depth_mm - thickness_mm
                if ped_height > 0:
                    self._p_h.setValue(round(ped_height))
        except Exception:
            pass

    def _update_diagrams(self):
        fw = self._f_w.value()
        fl = self._f_l.value()
        ft = self._f_t.value()
        pw = self._p_w.value()
        plen = self._p_l.value()
        ph = self._p_h.value()
        for d in [self._plan, self._section, self._iso3d]:
            d.update_dims(fw, fl, ft, pw, plen, ph)

    @property
    def config(self) -> dict:
        return {
            "width": self._f_w.value(),
            "length": self._f_l.value(),
            "thickness": self._f_t.value(),
            "pedestal_width": self._p_w.value(),
            "pedestal_length": self._p_l.value(),
            "pedestal_height": self._p_h.value(),
        }


# ──────────────────────────────────────────────────────────────
# Main panel
# ──────────────────────────────────────────────────────────────

class FoundationsPanel(QWidget):
    """Panel with 3 sub-tabs for foundation types, name input, list, and send."""

    send_requested = Signal(dict)  # full config dict
    placement_mode_changed = Signal(bool)  # True = enter, False = exit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ControlPanel")
        self._placement_active = False
        # Currently selected foundation for placement (from list)
        self._active_foundation: dict | None = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- Title ---
        title = QLabel("Cimentaciones")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#007acc;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # --- Sub-tabs for 3 footing types ---
        self._sub_tabs = QTabWidget()
        self._sub_tabs.setObjectName("FoundationSubTabs")

        self._tab_central = _FoundationTypeTab("central")
        self._tab_esquinera = _FoundationTypeTab("esquinera")
        self._tab_lindero = _FoundationTypeTab("lindero")

        self._sub_tabs.addTab(self._tab_central, "Central")
        self._sub_tabs.addTab(self._tab_esquinera, "Esquinera")
        self._sub_tabs.addTab(self._tab_lindero, "Lindero")

        root.addWidget(self._sub_tabs, stretch=1)

        # --- Name input + Add button ---
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        lbl_name = QLabel("Nombre:")
        lbl_name.setFixedWidth(55)
        name_row.addWidget(lbl_name)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Ej: Z-01")
        name_row.addWidget(self._name_input)

        self._btn_add = QPushButton("Agregar")
        self._btn_add.setObjectName("AddButton")
        self._btn_add.setFixedWidth(75)
        name_row.addWidget(self._btn_add)
        root.addLayout(name_row)

        # --- List of added foundations ---
        list_lbl = QLabel("Cimentaciones configuradas:")
        list_lbl.setStyleSheet("color:#999; font-size:11px;")
        root.addWidget(list_lbl)

        self._foundation_list = QListWidget()
        self._foundation_list.setMaximumHeight(90)
        self._foundation_list.setStyleSheet(
            "QListWidget{background:#2a2a2a; color:#ddd; font-size:11px;}"
            "QListWidget::item:selected{background:#3a5a7a;}"
        )
        root.addWidget(self._foundation_list)

        # --- Placement mode button ---
        place_row = QHBoxLayout()
        place_row.setSpacing(6)

        self._btn_place = QPushButton("Modo Colocar")
        self._btn_place.setObjectName("AddButton")
        self._btn_place.setCheckable(True)
        self._btn_place.setToolTip(
            "Selecciona una cimentacion de la lista y haz clic\n"
            "en las intersecciones del grid para asignarla"
        )
        place_row.addWidget(self._btn_place)

        self._btn_clear_placed = QPushButton("Limpiar Grid")
        self._btn_clear_placed.setObjectName("ResetButton")
        self._btn_clear_placed.setToolTip("Quitar todas las cimentaciones del grid")
        place_row.addWidget(self._btn_clear_placed)

        self._btn_remove = QPushButton("Quitar")
        self._btn_remove.setObjectName("ResetButton")
        self._btn_remove.setToolTip("Quitar cimentacion seleccionada de la lista")
        place_row.addWidget(self._btn_remove)
        root.addLayout(place_row)

        # --- Placement info ---
        self._place_info = QLabel("")
        self._place_info.setStyleSheet("color:#ff8a65; font-size:11px;")
        self._place_info.setWordWrap(True)
        root.addWidget(self._place_info)

        # --- Send button ---
        self._btn_send = QPushButton("Crear Cimentaciones en Revit")
        self._btn_send.setObjectName("SendButton")
        self._btn_send.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self._btn_send)

        # --- Progress ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setFixedHeight(20)
        root.addWidget(self._progress)

        # --- Status ---
        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

    def _connect_signals(self):
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_send.clicked.connect(self._on_send)
        self._btn_place.toggled.connect(self._on_placement_toggled)
        self._btn_clear_placed.clicked.connect(self._on_clear_placed)
        self._foundation_list.currentRowChanged.connect(self._on_list_selection_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add(self):
        name = self._name_input.text().strip()
        if not name:
            self.set_status("Ingrese un nombre para la cimentacion.", False)
            return

        # Get current sub-tab type
        idx = self._sub_tabs.currentIndex()
        tab_names = ["central", "esquinera", "lindero"]
        ftype = tab_names[idx]

        # Get config from current tab
        tab = [self._tab_central, self._tab_esquinera, self._tab_lindero][idx]
        config = tab.config

        # Build display text
        display = "%s | %s | %dx%d  Ped:%dx%d h:%d" % (
            name, ftype[0].upper(),
            int(config["width"]), int(config["length"]),
            int(config["pedestal_width"]), int(config["pedestal_length"]),
            int(config["pedestal_height"]),
        )

        item = QListWidgetItem(display)
        item.setData(Qt.UserRole, {
            "name": name,
            "type": ftype,
            **config,
        })
        self._foundation_list.addItem(item)
        self._foundation_list.setCurrentItem(item)
        self._name_input.clear()
        self.set_status("Agregada. Seleccionala y usa 'Modo Colocar' para asignar en el grid.", True)

    def _on_remove(self):
        for item in self._foundation_list.selectedItems():
            self._foundation_list.takeItem(self._foundation_list.row(item))

    def _on_placement_toggled(self, checked: bool):
        self._placement_active = checked
        if checked:
            # Check that a foundation is selected
            current = self._foundation_list.currentItem()
            if current is None:
                self._btn_place.setChecked(False)
                self.set_status("Selecciona una cimentacion de la lista primero.", False)
                return
            self._active_foundation = current.data(Qt.UserRole)
            name = self._active_foundation.get("name", "")
            self._place_info.setText(
                f"Colocando: {name}\nHaz clic en las intersecciones del grid"
            )
            self._btn_place.setStyleSheet("background:#ff8a65; color:#1e1e1e; font-weight:bold;")
        else:
            self._active_foundation = None
            self._place_info.setText("")
            self._btn_place.setStyleSheet("")
        self.placement_mode_changed.emit(checked)

    def _on_list_selection_changed(self, row: int):
        if self._placement_active and row >= 0:
            item = self._foundation_list.item(row)
            if item:
                self._active_foundation = item.data(Qt.UserRole)
                name = self._active_foundation.get("name", "")
                self._place_info.setText(
                    f"Colocando: {name}\nHaz clic en las intersecciones del grid"
                )

    def _on_clear_placed(self):
        """Signal to clear all placed foundations from canvas."""
        self._clear_placed_requested = True
        # This will be connected externally to canvas.clear_foundations()

    def _on_send(self):
        self.send_requested.emit(self._build_send_config())

    def _build_send_config(self) -> dict:
        """Build config dict from the list of added foundations."""
        items_by_type = {"central": [], "esquinera": [], "lindero": []}
        for i in range(self._foundation_list.count()):
            data = self._foundation_list.item(i).data(Qt.UserRole)
            ftype = data.get("type", "central")
            items_by_type[ftype].append(data)

        config = {}
        for ftype, tab in [("central", self._tab_central),
                            ("esquinera", self._tab_esquinera),
                            ("lindero", self._tab_lindero)]:
            if items_by_type[ftype]:
                d = items_by_type[ftype][0]
                config[ftype] = {
                    "width": d["width"],
                    "length": d["length"],
                    "thickness": d["thickness"],
                    "pedestal_width": d["pedestal_width"],
                    "pedestal_length": d["pedestal_length"],
                    "pedestal_height": d["pedestal_height"],
                }
            else:
                config[ftype] = tab.config

        all_names = []
        for i in range(self._foundation_list.count()):
            data = self._foundation_list.item(i).data(Qt.UserRole)
            all_names.append(data.get("name", ""))
        config["foundation_names"] = all_names

        return config

    # ------------------------------------------------------------------
    # Called by MainWindow when canvas intersection is clicked
    # ------------------------------------------------------------------

    def get_active_foundation(self) -> dict | None:
        """Return the currently selected foundation for placement, or None."""
        if self._placement_active and self._active_foundation:
            return dict(self._active_foundation)
        return None

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def set_sending(self, active: bool):
        self._progress.setVisible(active)
        self._btn_send.setEnabled(not active)
        if active:
            self._status_label.setText("")

    def set_status(self, text: str, success: bool):
        color = "#4ec94e" if success else "#ef5350"
        self._status_label.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_label.setText(text)
