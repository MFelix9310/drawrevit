"""HTTP client for creating foundations in Revit via pyRevit Routes."""

from __future__ import annotations

import requests
from PySide6.QtCore import QThread, Signal

BASE_URL = "http://localhost:48884/grid-api"
TIMEOUT_S = 120


class FoundationSenderThread(QThread):
    """Sends foundation configuration to Revit to create footings at grid intersections."""

    finished = Signal(bool, str)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config

    def run(self):
        try:
            resp = requests.post(
                f"{BASE_URL}/create_foundations/",
                json=self._config,
                timeout=TIMEOUT_S,
            )
            if resp.ok:
                data = resp.json()
                total = data.get("total", 0)
                central = data.get("central", 0)
                esquinera = data.get("esquinera", 0)
                lindero = data.get("lindero", 0)
                pedestals = data.get("pedestals", 0)
                dbg = data.get("debug", [])
                msg = (
                    f"\u2713 {total} zapatas | {pedestals} pedestales\n"
                    f"DEBUG: {' | '.join(dbg)}"
                )
                self.finished.emit(True, msg)
            else:
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    pass
                error = data.get("error", resp.text[:200])
                dbg = data.get("debug", [])
                tb = data.get("traceback", "")
                msg = f"Error {resp.status_code}: {error}"
                if dbg:
                    msg += f"\nDEBUG: {' | '.join(dbg)}"
                if tb:
                    msg += f"\n{tb[:400]}"
                self.finished.emit(False, msg)
        except requests.ConnectionError:
            self.finished.emit(False, "No se pudo conectar con Revit.")
        except requests.Timeout:
            self.finished.emit(False, "Timeout: Revit no respondio (puede tomar tiempo con muchos grids).")
        except Exception as exc:
            self.finished.emit(False, f"Error: {exc}")
