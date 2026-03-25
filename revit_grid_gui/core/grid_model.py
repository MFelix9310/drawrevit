"""Grid model: computes coordinates from grid counts and spacing values."""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import List


@dataclass
class GridLine:
    name: str
    position: float  # metres


@dataclass
class GridModel:
    """Holds the current grid configuration and computes derived data."""

    num_x: int = 4
    num_y: int = 3
    spacings_x: List[float] = field(default_factory=lambda: [6.0] * 3)
    spacings_y: List[float] = field(default_factory=lambda: [6.0] * 2)
    extent: float = 5.0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _letter_name(index: int) -> str:
        """Return A..Z, AA, AB... for index >= 26."""
        result = ""
        i = index
        while True:
            result = string.ascii_uppercase[i % 26] + result
            i = i // 26 - 1
            if i < 0:
                break
        return result

    # ------------------------------------------------------------------
    # Computed grid lines
    # ------------------------------------------------------------------

    def grids_x(self) -> List[GridLine]:
        lines: List[GridLine] = []
        pos = 0.0
        for i in range(self.num_x):
            lines.append(GridLine(name=self._letter_name(i), position=pos))
            if i < len(self.spacings_x):
                pos += self.spacings_x[i]
        return lines

    def grids_y(self) -> List[GridLine]:
        lines: List[GridLine] = []
        pos = 0.0
        for i in range(self.num_y):
            lines.append(GridLine(name=str(i + 1), position=pos))
            if i < len(self.spacings_y):
                pos += self.spacings_y[i]
        return lines

    def bounding_box(self):
        """Return (x_min, x_max, y_min, y_max) of the grid lines."""
        gx = self.grids_x()
        gy = self.grids_y()
        x_min = gx[0].position if gx else 0.0
        x_max = gx[-1].position if gx else 0.0
        y_min = gy[0].position if gy else 0.0
        y_max = gy[-1].position if gy else 0.0
        return x_min, x_max, y_min, y_max

    # ------------------------------------------------------------------
    # JSON payload for Revit
    # ------------------------------------------------------------------

    def to_revit_payload(self) -> dict:
        return {
            "grids_x": [{"name": g.name, "x": round(g.position, 4)} for g in self.grids_x()],
            "grids_y": [{"name": g.name, "y": round(g.position, 4)} for g in self.grids_y()],
            "extent": self.extent,
        }
