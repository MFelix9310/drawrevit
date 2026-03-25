# DrawRevit - Grid Generator GUI

Desktop application built with PySide6 for configuring structural grids, managing levels, and loading families in Autodesk Revit 2024 via pyRevit Routes API.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.5+-green)
![Revit](https://img.shields.io/badge/Revit-2024-orange)
![pyRevit](https://img.shields.io/badge/pyRevit-Routes_Beta-purple)

## Features

### Grids Tab
- Configure X and Y grid counts (1-20) with custom spacing per axis
- Real-time canvas preview with grid lines, labels, dimension annotations, and intersection dots
- Letter naming (A, B, C...) for vertical grids and numeric naming (1, 2, 3...) for horizontal grids
- Send grid configuration to Revit with one click

### Levels Tab
- Add, remove, and modify levels with name and elevation
- Fetch existing levels from Revit
- Replace mode: delete all existing levels and create new ones
- Automatic creation of floor plan views (ViewPlans) for each new level
- Automatic alignment of level lines with grid extents in elevation views
- Automatic unit conversion to meters

### Families Tab
- Browse and select multiple `.rfa` family files
- Batch load families into the active Revit document

## Architecture

```
revit_grid_gui/
├── main.py                    # Entry point, loads QSS theme
├── requirements.txt           # Python dependencies
├── ui/
│   ├── main_window.py         # Main window with QTabWidget (3 tabs)
│   ├── control_panel.py       # Grid configuration controls
│   ├── canvas_widget.py       # pyqtgraph real-time grid preview
│   ├── families_panel.py      # Family loading interface
│   └── levels_panel.py        # Level management interface
├── core/
│   ├── grid_model.py          # Grid coordinate calculation & JSON payload
│   ├── revit_client.py        # QThread HTTP client for grids
│   ├── family_client.py       # QThread HTTP client for families
│   └── level_client.py        # QThread HTTP client for levels
├── styles/
│   └── dark_theme.qss         # Dark theme stylesheet
└── pyrevit_extension/
    └── grid-api.extension/
        └── startup.py         # pyRevit Routes API endpoints (IronPython 2.7)
```

## Requirements

- **Python 3.10+** with PySide6, pyqtgraph, requests, numpy
- **Autodesk Revit 2024**
- **pyRevit** with Routes (Beta) enabled on port 48884

## Installation

### 1. Python GUI

```bash
cd revit_grid_gui
pip install -r requirements.txt
python main.py
```

### 2. pyRevit Extension

Copy the extension folder to pyRevit's extensions directory:

```powershell
# PowerShell (Admin)
New-Item -ItemType Directory -Path "$env:APPDATA\pyRevit\Extensions\grid-api.extension" -Force
Copy-Item "pyrevit_extension\grid-api.extension\startup.py" "$env:APPDATA\pyRevit\Extensions\grid-api.extension\startup.py" -Force
```

Then in Revit: **pyRevit > Reload**

### 3. Enable pyRevit Routes

1. Open Revit with pyRevit installed
2. Go to **pyRevit > Settings > Routes**
3. Enable Routes API on port **48884**
4. Restart Revit

## API Endpoints

All endpoints run on `http://localhost:48884/grid-api/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/create_grids/` | Create grid lines in Revit |
| POST | `/load_families/` | Load .rfa family files |
| GET | `/get_levels/` | Fetch current levels |
| POST | `/set_levels/` | Create/update/delete levels |
| POST | `/align_levels/` | Align level lines with grids |
| POST | `/set_units_meters/` | Set project units to meters |

## Technical Details

### Failure Handling

The `startup.py` implements a custom `IFailuresPreprocessor` (`LevelDeleteFailureHandler`) that handles both Warning and Error severity failures from the Revit API. This solves the deadlock issue where `doc.Delete()` on levels with associated views would generate Error-severity failures that block the pyRevit Routes thread indefinitely.

Key insight: `DeleteWarning()` only works for Warning severity. Error-severity failures require `ResolveFailure()` + `FailureProcessingResult.ProceedWithCommit`.

### Level Alignment

After creating levels, the API automatically aligns level datum lines with grid extents in elevation views using `DatumPlane.SetCurveInView()` with Model extents. Grid lines are extended vertically so bubbles appear above the highest level.

## License

MIT
