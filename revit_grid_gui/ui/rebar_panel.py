"""Panel for configuring reinforcement steel (rebar) in zapata and pedestal."""

from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

BAR_SIZES_MM = [8, 10, 12, 14, 16, 18, 20, 22, 25, 32]
BAR_SIZES_IN = [
    '5/16"', '3/8"', '1/2"', '9/16"', '5/8"',
    '3/4"', '13/16"', '7/8"', '1"', '1-1/4"',
]

_BG = QColor("#1e1e1e")
_FOOTING_COLOR = QColor("#5a7fa5")
_FOOTING_EDGE = QColor("#7aafdf")
_PEDESTAL_COLOR = QColor("#a57f5a")
_PEDESTAL_EDGE = QColor("#dfaf7a")
_DIM_COLOR = QColor("#888888")
_REBAR_ZAPATA = QColor("#44dd44")
_REBAR_LONG = QColor("#dd4444")
_REBAR_STIRRUP = QColor("#dddd44")
_LABEL_FONT = None


def _get_label_font():
    """Lazy-init label font to avoid QFont before QApplication exists."""
    global _LABEL_FONT
    if _LABEL_FONT is None:
        _LABEL_FONT = QFont("Segoe UI", 7)
    return _LABEL_FONT


def _bar_display_items() -> list[str]:
    """Build combo-box display strings: '12 mm (1/2\")'."""
    items = []
    for mm, inch in zip(BAR_SIZES_MM, BAR_SIZES_IN):
        items.append(f"{mm} mm ({inch})")
    return items


# ──────────────────────────────────────────────────────────────
# 3-D isometric diagram with rebar
# ──────────────────────────────────────────────────────────────

class RebarIso3DDiagram(QWidget):
    """Isometric 3D view of zapata + pedestal with rebar lines."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Foundation dims (mm)
        self.f_w = 1500.0
        self.f_l = 1500.0
        self.f_t = 400.0
        # Pedestal dims (mm)
        self.p_w = 400.0
        self.p_l = 400.0
        self.p_h = 600.0
        # Type
        self.ftype = "central"

        # Rebar config — zapata
        self.zap_spacing_x = 200.0
        self.zap_spacing_y = 200.0
        self.zap_cover = 75.0
        self.zap_bar_diam = 12

        # Rebar config — pedestal
        self.ped_bars_per_side = 2
        self.ped_stirrup_spacing = 150.0
        self.ped_cover = 40.0
        self.ped_long_diam = 12
        self.ped_stirrup_diam = 8

    # ── coordinate helpers ──

    def _iso(self, x, y, z, cx, cy, scale):
        """Convert 3D coords to 2D isometric."""
        ix = (x - y) * math.cos(math.radians(30)) * scale
        iy = -(x + y) * math.sin(math.radians(30)) * scale - z * scale
        return QPointF(cx + ix, cy - iy)

    def _draw_box(self, p, cx, cy, scale, ox, oy, oz, bw, bl, bh, fill, edge):
        """Draw an isometric box (visible faces only)."""
        corners = []
        for dz in [0, bh]:
            for dy in [0, bl]:
                for dx in [0, bw]:
                    corners.append(self._iso(ox + dx, oy + dy, oz + dz, cx, cy, scale))

        top = QPolygonF([corners[4], corners[5], corners[7], corners[6]])
        right = QPolygonF([corners[1], corners[3], corners[7], corners[5]])
        front = QPolygonF([corners[2], corners[3], corners[7], corners[6]])

        light = QColor(fill)
        light.setAlpha(220)
        dark = QColor(fill)
        dark.setRed(max(0, dark.red() - 30))
        dark.setGreen(max(0, dark.green() - 30))
        dark.setBlue(max(0, dark.blue() - 30))
        dark.setAlpha(220)

        pen = QPen(edge, 1.0)

        p.setPen(pen)
        p.setBrush(QBrush(dark))
        p.drawPolygon(front)

        p.setBrush(QBrush(fill))
        p.drawPolygon(right)

        p.setBrush(QBrush(light))
        p.drawPolygon(top)

    # ── rebar drawing helpers ──

    def _draw_zapata_rebar(self, p, cx, cy, scale, fox, foy, foz):
        """Draw a grid of rebar lines inside the zapata."""
        cover = self.zap_cover
        sx = self.zap_spacing_x
        sy = self.zap_spacing_y

        inner_x0 = fox + cover
        inner_x1 = fox + self.f_w - cover
        inner_y0 = foy + cover
        inner_y1 = foy + self.f_l - cover

        # Rebar sits near the bottom of the footing
        rebar_z = foz + cover

        pen = QPen(_REBAR_ZAPATA, 1.2)
        p.setPen(pen)

        # Lines running in X direction (spaced along Y)
        y = inner_y0
        while y <= inner_y1 + 0.1:
            pt_a = self._iso(inner_x0, y, rebar_z, cx, cy, scale)
            pt_b = self._iso(inner_x1, y, rebar_z, cx, cy, scale)
            p.drawLine(pt_a, pt_b)
            y += sy

        # Lines running in Y direction (spaced along X)
        x = inner_x0
        while x <= inner_x1 + 0.1:
            pt_a = self._iso(x, inner_y0, rebar_z, cx, cy, scale)
            pt_b = self._iso(x, inner_y1, rebar_z, cx, cy, scale)
            p.drawLine(pt_a, pt_b)
            x += sx

    def _draw_pedestal_rebar(self, p, cx, cy, scale, pox, poy, poz):
        """Draw longitudinal bars and stirrups in the pedestal."""
        cover = self.ped_cover
        pw = self.p_w
        pl = self.p_l
        ph = self.p_h
        n = self.ped_bars_per_side
        stir_sp = self.ped_stirrup_spacing

        # Inner bounds
        ix0 = pox + cover
        ix1 = pox + pw - cover
        iy0 = poy + cover
        iy1 = poy + pl - cover

        z_bot = poz + cover
        z_top = poz + ph - cover

        # ── Longitudinal bars (vertical lines at perimeter positions) ──
        pen_long = QPen(_REBAR_LONG, 1.4)
        p.setPen(pen_long)

        bar_positions = []  # (x, y) in 3D

        if n <= 1:
            # Minimum: 4 corner bars
            positions_x = [ix0, ix1]
            positions_y = [iy0, iy1]
        else:
            # n bars per side: corners + intermediates
            positions_x = []
            positions_y = []
            for i in range(n):
                frac = i / max(n - 1, 1)
                positions_x.append(ix0 + frac * (ix1 - ix0))
                positions_y.append(iy0 + frac * (iy1 - iy0))

        # Bars along the 4 sides (avoiding duplicate corners)
        # Bottom side (y = iy0): all x positions
        for bx in positions_x:
            bar_positions.append((bx, iy0))
        # Top side (y = iy1): all x positions
        for bx in positions_x:
            bar_positions.append((bx, iy1))
        # Left side (x = ix0): intermediate y positions (skip corners)
        for by in positions_y[1:-1]:
            bar_positions.append((ix0, by))
        # Right side (x = ix1): intermediate y positions (skip corners)
        for by in positions_y[1:-1]:
            bar_positions.append((ix1, by))

        for bx, by in bar_positions:
            pt_bot = self._iso(bx, by, z_bot, cx, cy, scale)
            pt_top = self._iso(bx, by, z_top, cx, cy, scale)
            p.drawLine(pt_bot, pt_top)

        # ── Stirrups (horizontal rectangles at intervals along height) ──
        pen_stir = QPen(_REBAR_STIRRUP, 1.0)
        p.setPen(pen_stir)

        z = z_bot
        while z <= z_top + 0.1:
            c0 = self._iso(ix0, iy0, z, cx, cy, scale)
            c1 = self._iso(ix1, iy0, z, cx, cy, scale)
            c2 = self._iso(ix1, iy1, z, cx, cy, scale)
            c3 = self._iso(ix0, iy1, z, cx, cy, scale)
            poly = QPolygonF([c0, c1, c2, c3, c0])
            p.drawPolyline(poly)
            z += stir_sp

    # ── paint ──

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), _BG)

        w, h = self.width(), self.height()
        cx = w / 2.0
        cy = h * 0.65

        total_h = self.f_t + self.p_h
        max_dim = max(self.f_w, self.f_l, total_h)
        scale = min(w, h) * 0.28 / max_dim if max_dim > 0 else 0.01

        fw, fl, ft = self.f_w, self.f_l, self.f_t
        pw_d, pl_d, ph_d = self.p_w, self.p_l, self.p_h

        # Foundation origin (centered)
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

        # Draw foundation box
        self._draw_box(p, cx, cy, scale, fox, foy, foz, fw, fl, ft,
                        _FOOTING_COLOR, _FOOTING_EDGE)

        # Draw zapata rebar
        self._draw_zapata_rebar(p, cx, cy, scale, fox, foy, foz)

        # Draw pedestal box
        self._draw_box(p, cx, cy, scale, pox, poy, ft, pw_d, pl_d, ph_d,
                        _PEDESTAL_COLOR, _PEDESTAL_EDGE)

        # Draw pedestal rebar
        self._draw_pedestal_rebar(p, cx, cy, scale, pox, poy, ft)

        # Label
        p.setPen(QPen(_DIM_COLOR))
        p.setFont(_get_label_font())
        p.drawText(QRectF(0, h - 14, w, 14), Qt.AlignCenter, "REFUERZO 3D")
        p.end()

    # ── public update methods ──

    def set_foundation_dims(self, width, length, thickness, ped_w, ped_l, ped_h):
        """Receive dimensions from the selected foundation."""
        self.f_w = width
        self.f_l = length
        self.f_t = thickness
        self.p_w = ped_w
        self.p_l = ped_l
        self.p_h = ped_h
        self.update()

    def set_foundation_type(self, ftype: str):
        self.ftype = ftype
        self.update()

    def set_zapata_rebar(self, bar_diam, spacing_x, spacing_y, cover):
        self.zap_bar_diam = bar_diam
        self.zap_spacing_x = spacing_x
        self.zap_spacing_y = spacing_y
        self.zap_cover = cover
        self.update()

    def set_pedestal_rebar(self, long_diam, bars_per_side, stirrup_diam,
                           stirrup_spacing, cover):
        self.ped_long_diam = long_diam
        self.ped_bars_per_side = bars_per_side
        self.ped_stirrup_diam = stirrup_diam
        self.ped_stirrup_spacing = stirrup_spacing
        self.ped_cover = cover
        self.update()


# ──────────────────────────────────────────────────────────────
# Main panel
# ──────────────────────────────────────────────────────────────

class RebarPanel(QWidget):
    """Panel for configuring reinforcement steel in zapata and pedestal."""

    send_rebar_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RebarPanel")
        self._bar_items = _bar_display_items()
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # --- Title ---
        title = QLabel("Refuerzo (Acero)")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#007acc;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # --- Scroll area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none; background:transparent;}"
        )
        scroll_content = QWidget()
        self._inner = QVBoxLayout(scroll_content)
        self._inner.setContentsMargins(0, 0, 0, 0)
        self._inner.setSpacing(8)
        scroll.setWidget(scroll_content)

        # --- 3D Diagram ---
        self._diagram = RebarIso3DDiagram()
        self._inner.addWidget(self._diagram)

        # --- Foundation type selector ---
        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        lbl_type = QLabel("Tipo:")
        lbl_type.setFixedWidth(95)
        type_row.addWidget(lbl_type)
        self._combo_ftype = QComboBox()
        self._combo_ftype.addItems(["Central", "Esquinera", "Lindero"])
        type_row.addWidget(self._combo_ftype)
        self._inner.addLayout(type_row)

        # --- Zapata rebar group ---
        zap_group = QGroupBox("Refuerzo Zapata")
        zap_group.setStyleSheet("QGroupBox{font-weight:bold; color:#5a7fa5;}")
        zl = QVBoxLayout(zap_group)
        zl.setSpacing(4)
        zl.setContentsMargins(8, 14, 8, 6)

        self._zap_bar = self._make_combo_row(zl, "Diametro barra:", self._bar_items, 2)
        self._zap_sx = self._make_spinbox_row(zl, "Espaciado X (mm):", 100, 500, 200)
        self._zap_sy = self._make_spinbox_row(zl, "Espaciado Y (mm):", 100, 500, 200)
        self._zap_cover = self._make_spinbox_row(zl, "Recubrimiento (mm):", 25, 150, 75)
        self._inner.addWidget(zap_group)

        # --- Pedestal rebar group ---
        ped_group = QGroupBox("Refuerzo Pedestal")
        ped_group.setStyleSheet("QGroupBox{font-weight:bold; color:#a57f5a;}")
        pl = QVBoxLayout(ped_group)
        pl.setSpacing(4)
        pl.setContentsMargins(8, 14, 8, 6)

        self._ped_long_bar = self._make_combo_row(pl, "Barra longitudinal:", self._bar_items, 2)
        self._ped_n_bars = self._make_spinbox_row(pl, "Barras por lado:", 2, 10, 2)
        self._ped_stirrup_bar = self._make_combo_row(pl, "Estribo diametro:", self._bar_items, 0)
        self._ped_stirrup_sp = self._make_spinbox_row(pl, "Espaciado estribo (mm):", 50, 400, 150)
        self._ped_cover = self._make_spinbox_row(pl, "Recubrimiento (mm):", 20, 100, 40)
        self._inner.addWidget(ped_group)

        # --- Total bar count info ---
        self._lbl_total_bars = QLabel("Total barras longitudinales: 4")
        self._lbl_total_bars.setStyleSheet("color:#999; font-size:11px;")
        self._inner.addWidget(self._lbl_total_bars)

        self._inner.addStretch(1)

        root.addWidget(scroll, stretch=1)

        # --- Create button ---
        self._btn_send = QPushButton("Crear Refuerzo en Revit")
        self._btn_send.setObjectName("SendButton")
        self._btn_send.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_send.setStyleSheet(
            "QPushButton {"
            "  background-color: #2e7d32; color: white; border: none;"
            "  border-radius: 6px; padding: 10px; font-size: 14px; font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #388e3c; }"
            "QPushButton:pressed { background-color: #1b5e20; }"
            "QPushButton:disabled { background-color: #555; color: #999; }"
        )
        root.addWidget(self._btn_send)

        # --- Status ---
        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusLabel")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Widget factories
    # ------------------------------------------------------------------

    @staticmethod
    def _make_combo_row(layout, label_text: str, items: list[str],
                        default_index: int = 0) -> QComboBox:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(130)
        row.addWidget(lbl)
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentIndex(default_index)
        row.addWidget(combo)
        layout.addLayout(row)
        return combo

    @staticmethod
    def _make_spinbox_row(layout, label_text: str, lo: int, hi: int,
                          default: int) -> QSpinBox:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(130)
        row.addWidget(lbl)
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(default)
        spin.setSingleStep(10 if hi <= 500 else 50)
        row.addWidget(spin)
        layout.addLayout(row)
        return spin

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # Foundation type
        self._combo_ftype.currentIndexChanged.connect(self._on_ftype_changed)

        # Zapata rebar controls
        self._zap_bar.currentIndexChanged.connect(self._on_zapata_changed)
        self._zap_sx.valueChanged.connect(self._on_zapata_changed)
        self._zap_sy.valueChanged.connect(self._on_zapata_changed)
        self._zap_cover.valueChanged.connect(self._on_zapata_changed)

        # Pedestal rebar controls
        self._ped_long_bar.currentIndexChanged.connect(self._on_pedestal_changed)
        self._ped_n_bars.valueChanged.connect(self._on_pedestal_changed)
        self._ped_stirrup_bar.currentIndexChanged.connect(self._on_pedestal_changed)
        self._ped_stirrup_sp.valueChanged.connect(self._on_pedestal_changed)
        self._ped_cover.valueChanged.connect(self._on_pedestal_changed)

        # Send button
        self._btn_send.clicked.connect(self._on_send)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_ftype_changed(self, index: int):
        ftype_map = {0: "central", 1: "esquinera", 2: "lindero"}
        self._diagram.set_foundation_type(ftype_map.get(index, "central"))

    def _on_zapata_changed(self):
        idx = self._zap_bar.currentIndex()
        bar_diam = BAR_SIZES_MM[idx] if 0 <= idx < len(BAR_SIZES_MM) else 12
        self._diagram.set_zapata_rebar(
            bar_diam,
            self._zap_sx.value(),
            self._zap_sy.value(),
            self._zap_cover.value(),
        )

    def _on_pedestal_changed(self):
        idx_long = self._ped_long_bar.currentIndex()
        idx_stir = self._ped_stirrup_bar.currentIndex()
        long_diam = BAR_SIZES_MM[idx_long] if 0 <= idx_long < len(BAR_SIZES_MM) else 12
        stir_diam = BAR_SIZES_MM[idx_stir] if 0 <= idx_stir < len(BAR_SIZES_MM) else 8
        n = self._ped_n_bars.value()

        self._diagram.set_pedestal_rebar(
            long_diam,
            n,
            stir_diam,
            self._ped_stirrup_sp.value(),
            self._ped_cover.value(),
        )

        # Update total bars label: 4 sides, n per side, minus 4 shared corners
        total = max(4, 4 * n - 4)
        self._lbl_total_bars.setText(f"Total barras longitudinales: {total}")

    def _on_send(self):
        self.send_rebar_requested.emit(self._build_config())

    # ------------------------------------------------------------------
    # Config building
    # ------------------------------------------------------------------

    def _build_config(self) -> dict:
        ftype_map = {0: "central", 1: "esquinera", 2: "lindero"}
        zap_bar_idx = self._zap_bar.currentIndex()
        ped_long_idx = self._ped_long_bar.currentIndex()
        ped_stir_idx = self._ped_stirrup_bar.currentIndex()
        n = self._ped_n_bars.value()
        total_bars = max(4, 4 * n - 4)

        return {
            "foundation_type": ftype_map.get(self._combo_ftype.currentIndex(), "central"),
            "zapata": {
                "bar_diameter_mm": BAR_SIZES_MM[zap_bar_idx],
                "bar_diameter_in": BAR_SIZES_IN[zap_bar_idx],
                "spacing_x_mm": self._zap_sx.value(),
                "spacing_y_mm": self._zap_sy.value(),
                "cover_mm": self._zap_cover.value(),
            },
            "pedestal": {
                "longitudinal_bar_diameter_mm": BAR_SIZES_MM[ped_long_idx],
                "longitudinal_bar_diameter_in": BAR_SIZES_IN[ped_long_idx],
                "bars_per_side": n,
                "total_longitudinal_bars": total_bars,
                "stirrup_diameter_mm": BAR_SIZES_MM[ped_stir_idx],
                "stirrup_diameter_in": BAR_SIZES_IN[ped_stir_idx],
                "stirrup_spacing_mm": self._ped_stirrup_sp.value(),
                "cover_mm": self._ped_cover.value(),
            },
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_foundation_dims(self, width, length, thickness, ped_w, ped_l, ped_h):
        """Receive foundation dimensions from external source (e.g. FoundationsPanel)."""
        self._diagram.set_foundation_dims(width, length, thickness, ped_w, ped_l, ped_h)

    def set_status(self, text: str, success: bool):
        color = "#4ec94e" if success else "#ef5350"
        self._status_label.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_label.setText(text)

    def set_sending(self, active: bool):
        self._btn_send.setEnabled(not active)
        if active:
            self._status_label.setText("")
