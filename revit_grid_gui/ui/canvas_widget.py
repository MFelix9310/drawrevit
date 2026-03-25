"""Canvas widget using pyqtgraph for real-time grid preview with foundation placement."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core.grid_model import GridModel

# Colours
GRID_X_COLOR = "#4fc3f7"
GRID_Y_COLOR = "#ef9a9a"
COTA_COLOR = "#ffd54f"
INTERSECTION_COLOR = "#888888"
BG_COLOR = "#1e1e1e"
SUBTLE_GRID_COLOR = (60, 60, 60, 80)

# Foundation placement colours
FOUNDATION_COLORS = {
    "central": "#5a7fa5",
    "esquinera": "#a57f5a",
    "lindero": "#7fa55a",
}
FOUNDATION_SELECTED_COLOR = "#ff8a65"

# Snap distance in data coordinates (metres)
SNAP_RADIUS = 1.5


class CanvasWidget(QWidget):
    """Real-time grid preview powered by pyqtgraph, with interactive foundation placement."""

    # Emitted when user clicks an intersection in placement mode
    # (grid_x_name, grid_y_name, x_pos, y_pos)
    intersection_clicked = Signal(str, str, float, float)

    def __init__(self, model: GridModel, parent=None):
        super().__init__(parent)
        self._model = model
        self._placement_mode = False
        # Dict of placed foundations: key=(grid_x_name, grid_y_name), value=dict with config
        self._placed_foundations: dict[tuple[str, str], dict] = {}
        self._foundation_items: list = []  # pyqtgraph items for foundation markers
        self._setup_ui()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        pg.setConfigOptions(antialias=True, background=BG_COLOR)

        self._pw = pg.PlotWidget()
        self._pw.setAspectLocked(True)
        self._pw.hideButtons()
        self._pw.setMenuEnabled(False)

        # subtle background grid
        self._pw.showGrid(x=True, y=True, alpha=0.12)

        # hide axes (we draw our own labels)
        for axis_name in ("left", "bottom", "top", "right"):
            self._pw.getAxis(axis_name).setStyle(showValues=False, tickLength=0)
            self._pw.getAxis(axis_name).setPen(pg.mkPen(color=(60, 60, 60), width=1))

        layout.addWidget(self._pw)

        # Connect mouse click
        self._pw.scene().sigMouseClicked.connect(self._on_mouse_clicked)

        # Storage for dynamic items
        self._items: list = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self):
        """Redraw the entire canvas from the current model state."""
        self._clear_items()

        gx = self._model.grids_x()
        gy = self._model.grids_y()

        if not gx or not gy:
            return

        x_min, x_max, y_min, y_max = self._model.bounding_box()
        ext = self._model.extent

        # --- Grid lines ------------------------------------------------

        for g in gx:
            line = pg.PlotCurveItem(
                x=[g.position, g.position],
                y=[y_min - ext, y_max + ext],
                pen=pg.mkPen(color=GRID_X_COLOR, width=1.5),
            )
            self._add(line)

        for g in gy:
            line = pg.PlotCurveItem(
                x=[x_min - ext, x_max + ext],
                y=[g.position, g.position],
                pen=pg.mkPen(color=GRID_Y_COLOR, width=1.5),
            )
            self._add(line)

        # --- Intersection dots -----------------------------------------

        xs = [g.position for g in gx]
        ys = [g.position for g in gy]
        pts_x, pts_y = [], []
        for x in xs:
            for y in ys:
                pts_x.append(x)
                pts_y.append(y)

        scatter = pg.ScatterPlotItem(
            x=pts_x,
            y=pts_y,
            size=6,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(INTERSECTION_COLOR),
        )
        self._add(scatter)

        # --- Labels ----------------------------------------------------

        label_offset = ext + 1.5

        # X labels (top & bottom)
        for g in gx:
            for y_pos in [y_max + label_offset, y_min - label_offset]:
                txt = pg.TextItem(
                    text=g.name,
                    color=GRID_X_COLOR,
                    anchor=(0.5, 0.5),
                )
                _f11b = pg.QtGui.QFont("Segoe UI", 11); _f11b.setBold(True); txt.setFont(_f11b)
                txt.setPos(g.position, y_pos)
                self._add(txt)

            # Circle bubbles at top
            bubble = pg.ScatterPlotItem(
                x=[g.position],
                y=[y_max + label_offset],
                size=24,
                pen=pg.mkPen(color=GRID_X_COLOR, width=1.5),
                brush=pg.mkBrush(30, 30, 30, 200),
                symbol="o",
            )
            self._add(bubble)

        # Y labels (left & right)
        for g in gy:
            for x_pos in [x_min - label_offset, x_max + label_offset]:
                txt = pg.TextItem(
                    text=g.name,
                    color=GRID_Y_COLOR,
                    anchor=(0.5, 0.5),
                )
                _f11b = pg.QtGui.QFont("Segoe UI", 11); _f11b.setBold(True); txt.setFont(_f11b)
                txt.setPos(x_pos, g.position)
                self._add(txt)

            bubble = pg.ScatterPlotItem(
                x=[x_min - label_offset],
                y=[g.position],
                size=24,
                pen=pg.mkPen(color=GRID_Y_COLOR, width=1.5),
                brush=pg.mkBrush(30, 30, 30, 200),
                symbol="o",
            )
            self._add(bubble)

        # --- Dimension lines (cotas) -----------------------------------

        cota_y = y_max + ext + 3.5  # X cotas above grid
        cota_x = x_min - ext - 3.5  # Y cotas left of grid

        # X spacings
        for i in range(len(gx) - 1):
            x0 = gx[i].position
            x1 = gx[i + 1].position
            mid = (x0 + x1) / 2
            dist = x1 - x0

            # line
            dim_line = pg.PlotCurveItem(
                x=[x0, x1],
                y=[cota_y, cota_y],
                pen=pg.mkPen(color=COTA_COLOR, width=1, style=pg.QtCore.Qt.DashLine),
            )
            self._add(dim_line)

            # ticks
            for xp in [x0, x1]:
                tick = pg.PlotCurveItem(
                    x=[xp, xp],
                    y=[cota_y - 0.4, cota_y + 0.4],
                    pen=pg.mkPen(color=COTA_COLOR, width=1.5),
                )
                self._add(tick)

            # text
            txt = pg.TextItem(
                text=f"{dist:.2f} m",
                color=COTA_COLOR,
                anchor=(0.5, 1.0),
            )
            txt.setFont(pg.QtGui.QFont("Segoe UI", 9))
            txt.setPos(mid, cota_y - 0.5)
            self._add(txt)

        # Y spacings
        for i in range(len(gy) - 1):
            y0 = gy[i].position
            y1 = gy[i + 1].position
            mid = (y0 + y1) / 2
            dist = y1 - y0

            dim_line = pg.PlotCurveItem(
                x=[cota_x, cota_x],
                y=[y0, y1],
                pen=pg.mkPen(color=COTA_COLOR, width=1, style=pg.QtCore.Qt.DashLine),
            )
            self._add(dim_line)

            for yp in [y0, y1]:
                tick = pg.PlotCurveItem(
                    x=[cota_x - 0.4, cota_x + 0.4],
                    y=[yp, yp],
                    pen=pg.mkPen(color=COTA_COLOR, width=1.5),
                )
                self._add(tick)

            txt = pg.TextItem(
                text=f"{dist:.2f} m",
                color=COTA_COLOR,
                anchor=(1.0, 0.5),
            )
            txt.setFont(pg.QtGui.QFont("Segoe UI", 9))
            txt.setPos(cota_x - 0.6, mid)
            self._add(txt)

        # --- Auto-fit --------------------------------------------------

        margin = ext + 6
        self._pw.setRange(
            xRange=(x_min - margin, x_max + margin),
            yRange=(y_min - margin, y_max + margin),
            padding=0,
        )

        # Re-draw foundation markers
        self._draw_foundation_markers()

    # ------------------------------------------------------------------
    # Foundation placement mode
    # ------------------------------------------------------------------

    def set_placement_mode(self, active: bool):
        """Enable/disable click-to-place foundation mode."""
        self._placement_mode = active
        if active:
            self._pw.setCursor(Qt.CrossCursor)
        else:
            self._pw.setCursor(Qt.ArrowCursor)

    def place_foundation(self, grid_x_name: str, grid_y_name: str, foundation_info: dict):
        """Mark an intersection with a foundation."""
        key = (grid_x_name, grid_y_name)
        self._placed_foundations[key] = foundation_info
        self._draw_foundation_markers()

    def remove_foundation(self, grid_x_name: str, grid_y_name: str):
        """Remove foundation from an intersection."""
        key = (grid_x_name, grid_y_name)
        if key in self._placed_foundations:
            del self._placed_foundations[key]
            self._draw_foundation_markers()

    def clear_foundations(self):
        """Remove all placed foundations from canvas."""
        self._placed_foundations.clear()
        self._draw_foundation_markers()

    def get_placed_foundations(self) -> dict:
        """Return dict of all placed foundations."""
        return dict(self._placed_foundations)

    # ------------------------------------------------------------------
    # Drawing foundation markers
    # ------------------------------------------------------------------

    def _draw_foundation_markers(self):
        """Draw colored squares and labels at placed foundation intersections."""
        # Remove old markers
        for item in self._foundation_items:
            self._pw.removeItem(item)
        self._foundation_items.clear()

        gx = self._model.grids_x()
        gy = self._model.grids_y()
        if not gx or not gy:
            return

        # Build position lookup
        x_pos_map = {g.name: g.position for g in gx}
        y_pos_map = {g.name: g.position for g in gy}

        for (gx_name, gy_name), info in self._placed_foundations.items():
            x = x_pos_map.get(gx_name)
            y = y_pos_map.get(gy_name)
            if x is None or y is None:
                continue

            ftype = info.get("type", "central")
            fname = info.get("name", "")
            color = FOUNDATION_COLORS.get(ftype, FOUNDATION_SELECTED_COLOR)

            # Draw filled square marker
            marker = pg.ScatterPlotItem(
                x=[x],
                y=[y],
                size=18,
                pen=pg.mkPen(color=color, width=2),
                brush=pg.mkBrush(color + "80"),  # semi-transparent
                symbol="s",  # square
            )
            self._pw.addItem(marker)
            self._foundation_items.append(marker)

            # Draw name label below the marker
            if fname:
                label = pg.TextItem(
                    text=fname,
                    color=color,
                    anchor=(0.5, 0.0),
                )
                _f7b = pg.QtGui.QFont("Segoe UI", 7); _f7b.setBold(True); label.setFont(_f7b)
                label.setPos(x, y - 1.2)
                self._pw.addItem(label)
                self._foundation_items.append(label)

            # Draw type indicator above
            type_label = pg.TextItem(
                text=ftype[0].upper(),  # C, E, L
                color="#ffffff",
                anchor=(0.5, 0.5),
            )
            _f6b = pg.QtGui.QFont("Segoe UI", 6); _f6b.setBold(True); type_label.setFont(_f6b)
            type_label.setPos(x, y)
            self._pw.addItem(type_label)
            self._foundation_items.append(type_label)

    # ------------------------------------------------------------------
    # Mouse click handler
    # ------------------------------------------------------------------

    def _on_mouse_clicked(self, evt):
        """Handle click events on the canvas."""
        if not self._placement_mode:
            return

        # Get click position in data coordinates
        pos = evt.scenePos()
        mouse_point = self._pw.plotItem.vb.mapSceneToView(pos)
        click_x = mouse_point.x()
        click_y = mouse_point.y()

        # Find nearest grid intersection
        gx = self._model.grids_x()
        gy = self._model.grids_y()

        if not gx or not gy:
            return

        best_dist = float("inf")
        best_gx_name = ""
        best_gy_name = ""
        best_x = 0.0
        best_y = 0.0

        for g_x in gx:
            for g_y in gy:
                dx = click_x - g_x.position
                dy = click_y - g_y.position
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_gx_name = g_x.name
                    best_gy_name = g_y.name
                    best_x = g_x.position
                    best_y = g_y.position

        # Check if within snap radius
        if best_dist <= SNAP_RADIUS:
            self.intersection_clicked.emit(best_gx_name, best_gy_name, best_x, best_y)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _add(self, item):
        self._pw.addItem(item)
        self._items.append(item)

    def _clear_items(self):
        for item in self._items:
            self._pw.removeItem(item)
        self._items.clear()
