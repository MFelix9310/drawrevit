"""HTTP client for managing levels in Revit via pyRevit Routes."""

from __future__ import annotations

import requests
from PySide6.QtCore import QThread, Signal

BASE_URL = "http://localhost:48884/grid-api"
TIMEOUT_S = 60


class LevelSenderThread(QThread):
    """Sends level data to Revit to create/update levels."""

    finished = Signal(bool, str)

    def __init__(self, levels: list[dict], replace: bool = True, parent=None):
        super().__init__(parent)
        self._levels = levels
        self._replace = replace

    def run(self):
        try:
            resp = requests.post(
                f"{BASE_URL}/set_levels/",
                json={"levels": self._levels, "replace": self._replace},
                timeout=TIMEOUT_S,
            )
            if resp.ok:
                data = resp.json()
                created = data.get("created", 0)
                updated = data.get("updated", 0)
                deleted = data.get("deleted", 0)
                msg_parts = []
                if deleted:
                    msg_parts.append(f"{deleted} eliminados")
                if created:
                    msg_parts.append(f"{created} creados")
                if updated:
                    msg_parts.append(f"{updated} actualizados")
                skipped = data.get("skipped", [])
                msg = "\u2713 Niveles: " + ", ".join(msg_parts) if msg_parts else "\u2713 Sin cambios"
                if skipped:
                    msg += f"\n(No se pudieron borrar: {', '.join(skipped)})"
                self.finished.emit(True, msg)
            else:
                self.finished.emit(False, f"Error {resp.status_code}: {resp.text[:200]}")
        except requests.ConnectionError:
            self.finished.emit(False, "No se pudo conectar con Revit.")
        except requests.Timeout:
            self.finished.emit(False, "Timeout: Revit no respondio.")
        except Exception as exc:
            self.finished.emit(False, f"Error: {exc}")


class LevelFetchThread(QThread):
    """Fetches current levels from Revit."""

    finished = Signal(bool, str, list)  # success, message, levels

    def run(self):
        try:
            resp = requests.get(
                f"{BASE_URL}/get_levels/",
                timeout=TIMEOUT_S,
            )
            if resp.ok:
                data = resp.json()
                levels = data.get("levels", [])
                self.finished.emit(True, f"\u2713 {len(levels)} niveles obtenidos", levels)
            else:
                self.finished.emit(False, f"Error {resp.status_code}: {resp.text[:200]}", [])
        except requests.ConnectionError:
            self.finished.emit(False, "No se pudo conectar con Revit.", [])
        except requests.Timeout:
            self.finished.emit(False, "Timeout: Revit no respondio.", [])
        except Exception as exc:
            self.finished.emit(False, f"Error: {exc}", [])
