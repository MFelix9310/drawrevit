"""HTTP client for loading families into Revit via pyRevit Routes."""

from __future__ import annotations

import requests
from PySide6.QtCore import QThread, Signal

REVIT_URL = "http://localhost:48884/grid-api/load_families/"
TIMEOUT_S = 30  # families can be large, allow more time


class FamilySenderThread(QThread):
    """Sends family paths to Revit on a background thread."""

    finished = Signal(bool, str)  # (success, message)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self._paths = paths

    def run(self):
        try:
            resp = requests.post(
                REVIT_URL,
                json={"families": self._paths},
                timeout=TIMEOUT_S,
            )
            if resp.ok:
                data = resp.json()
                loaded = data.get("loaded", 0)
                failed = data.get("failed", 0)
                msg = f"\u2713 {loaded} familias cargadas"
                if failed:
                    msg += f", {failed} fallaron"
                self.finished.emit(True, msg)
            else:
                self.finished.emit(
                    False, f"Error {resp.status_code}: {resp.text[:200]}"
                )
        except requests.ConnectionError:
            self.finished.emit(
                False,
                "No se pudo conectar con Revit. Verifica que Revit est\u00e9 abierto y pyRevit Routes activo.",
            )
        except requests.Timeout:
            self.finished.emit(False, "Timeout: Revit no respondi\u00f3.")
        except Exception as exc:
            self.finished.emit(False, f"Error inesperado: {exc}")
