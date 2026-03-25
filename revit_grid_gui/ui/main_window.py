"""Main application window — tab-based layout with Grids, Families, and Levels."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from core.grid_model import GridModel
from core.revit_client import RevitSenderThread
from core.family_client import FamilySenderThread
from core.level_client import LevelSenderThread, LevelFetchThread
from core.foundation_client import FoundationSenderThread
from ui.canvas_widget import CanvasWidget
from ui.control_panel import ControlPanel
from ui.families_panel import FamiliesPanel
from ui.levels_panel import LevelsPanel
from ui.foundations_panel import FoundationsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DrawRevit")
        self.setMinimumSize(1100, 700)

        self._model = GridModel()
        self._sender: RevitSenderThread | None = None
        self._family_sender: FamilySenderThread | None = None
        self._level_sender: LevelSenderThread | None = None
        self._level_fetcher: LevelFetchThread | None = None
        self._foundation_sender: FoundationSenderThread | None = None

        self._setup_ui()
        self._connect_signals()

        # Initial draw
        self._sync_model()
        self._canvas.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left side: Tabs ---
        left_container = QWidget()
        left_container.setFixedWidth(380)
        left_container.setObjectName("ControlPanel")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("MainTabs")

        # Tab 1: Grids
        self._grid_panel = ControlPanel()
        self._grid_panel.setFixedWidth(380)
        self._tabs.addTab(self._grid_panel, "Grids")

        # Tab 2: Cargar Familias
        self._families_panel = FamiliesPanel()
        self._families_panel.setFixedWidth(380)
        self._tabs.addTab(self._families_panel, "Familias")

        # Tab 3: Niveles
        self._levels_panel = LevelsPanel()
        self._levels_panel.setFixedWidth(380)
        self._tabs.addTab(self._levels_panel, "Niveles")

        # Tab 4: Cimentaciones
        self._foundations_panel = FoundationsPanel()
        self._foundations_panel.setFixedWidth(380)
        self._tabs.addTab(self._foundations_panel, "Cimentaciones")

        left_layout.addWidget(self._tabs)

        # --- Right side: Canvas ---
        self._canvas = CanvasWidget(self._model)

        main_layout.addWidget(left_container)
        main_layout.addWidget(self._canvas, stretch=1)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self):
        # Grids
        self._grid_panel.grids_changed.connect(self._on_grids_changed)
        self._grid_panel.send_requested.connect(self._on_send_grids)
        self._grid_panel.reset_requested.connect(self._on_grids_changed)

        # Families
        self._families_panel.send_requested.connect(self._on_send_families)

        # Levels
        self._levels_panel.send_requested.connect(self._on_send_levels)
        self._levels_panel.fetch_requested.connect(self._on_fetch_levels)

        # Foundations
        self._foundations_panel.send_requested.connect(self._on_send_foundations)
        self._foundations_panel.placement_mode_changed.connect(self._on_placement_mode)
        self._foundations_panel._btn_clear_placed.clicked.connect(self._canvas.clear_foundations)
        self._canvas.intersection_clicked.connect(self._on_intersection_clicked)

    @Slot()
    def _on_grids_changed(self):
        self._sync_model()
        self._canvas.refresh()

    def _sync_model(self):
        self._model.num_x = self._grid_panel.num_x
        self._model.num_y = self._grid_panel.num_y
        self._model.spacings_x = self._grid_panel.spacings_x
        self._model.spacings_y = self._grid_panel.spacings_y

    # ------------------------------------------------------------------
    # Revit: Grids
    # ------------------------------------------------------------------

    @Slot()
    def _on_send_grids(self):
        self._sync_model()
        payload = self._model.to_revit_payload()

        self._grid_panel.set_sending(True)

        self._sender = RevitSenderThread(payload, parent=self)
        self._sender.finished.connect(self._on_send_grids_finished)
        self._sender.start()

    @Slot(bool, str)
    def _on_send_grids_finished(self, success: bool, message: str):
        self._grid_panel.set_sending(False)
        self._grid_panel.set_status(message, success)
        self._sender = None

    # ------------------------------------------------------------------
    # Revit: Families
    # ------------------------------------------------------------------

    @Slot(list)
    def _on_send_families(self, paths: list[str]):
        self._families_panel.set_sending(True)

        self._family_sender = FamilySenderThread(paths, parent=self)
        self._family_sender.finished.connect(self._on_send_families_finished)
        self._family_sender.start()

    @Slot(bool, str)
    def _on_send_families_finished(self, success: bool, message: str):
        self._families_panel.set_sending(False)
        self._families_panel.set_status(message, success)
        self._family_sender = None

    # ------------------------------------------------------------------
    # Revit: Levels
    # ------------------------------------------------------------------

    @Slot(list, bool)
    def _on_send_levels(self, levels: list[dict], replace: bool = True):
        self._levels_panel.set_sending(True)

        self._level_sender = LevelSenderThread(levels, replace=replace, parent=self)
        self._level_sender.finished.connect(self._on_send_levels_finished)
        self._level_sender.start()

    @Slot(bool, str)
    def _on_send_levels_finished(self, success: bool, message: str):
        self._levels_panel.set_sending(False)
        self._levels_panel.set_status(message, success)
        self._level_sender = None

    @Slot()
    def _on_fetch_levels(self):
        self._levels_panel.set_sending(True)

        self._level_fetcher = LevelFetchThread(parent=self)
        self._level_fetcher.finished.connect(self._on_fetch_levels_finished)
        self._level_fetcher.start()

    @Slot(bool, str, list)
    def _on_fetch_levels_finished(self, success: bool, message: str, levels: list):
        self._levels_panel.set_sending(False)
        if success and levels:
            self._levels_panel.populate_from_revit(levels)
        self._levels_panel.set_status(message, success)
        self._level_fetcher = None

    # ------------------------------------------------------------------
    # Revit: Foundations
    # ------------------------------------------------------------------

    @Slot(bool)
    def _on_placement_mode(self, active: bool):
        self._canvas.set_placement_mode(active)

    @Slot(str, str, float, float)
    def _on_intersection_clicked(self, gx_name: str, gy_name: str, x: float, y: float):
        """Handle click on a grid intersection during placement mode."""
        foundation = self._foundations_panel.get_active_foundation()
        if foundation is None:
            return

        key = (gx_name, gy_name)
        existing = self._canvas.get_placed_foundations()

        if key in existing:
            # Toggle: remove if same foundation, replace if different
            if existing[key].get("name") == foundation.get("name"):
                self._canvas.remove_foundation(gx_name, gy_name)
                return

        self._canvas.place_foundation(gx_name, gy_name, foundation)

    @Slot(dict)
    def _on_send_foundations(self, config: dict):
        # Include per-intersection assignments from canvas
        placed = self._canvas.get_placed_foundations()
        if placed:
            assignments = []
            for (gx_name, gy_name), info in placed.items():
                assignments.append({
                    "grid_x": gx_name,
                    "grid_y": gy_name,
                    "name": info.get("name", ""),
                    "type": info.get("type", "central"),
                    "width": info.get("width", 1500),
                    "length": info.get("length", 1500),
                    "thickness": info.get("thickness", 400),
                    "pedestal_width": info.get("pedestal_width", 400),
                    "pedestal_length": info.get("pedestal_length", 400),
                    "pedestal_height": info.get("pedestal_height", 600),
                })
            config["assignments"] = assignments
            # Debug: print what each point sends
            for a in assignments:
                print("ASSIGNMENT: %s grid=%s,%s zapata=%sx%s ped=%sx%s h=%s" % (
                    a["name"], a["grid_x"], a["grid_y"],
                    a["width"], a["length"],
                    a["pedestal_width"], a["pedestal_length"],
                    a["pedestal_height"]))

        self._foundations_panel.set_sending(True)
        self._foundation_sender = FoundationSenderThread(config, parent=self)
        self._foundation_sender.finished.connect(self._on_send_foundations_finished)
        self._foundation_sender.start()

    @Slot(bool, str)
    def _on_send_foundations_finished(self, success: bool, message: str):
        self._foundations_panel.set_sending(False)
        self._foundations_panel.set_status(message, success)
        self._foundation_sender = None
