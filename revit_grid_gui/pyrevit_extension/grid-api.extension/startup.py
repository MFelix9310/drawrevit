# -*- coding: utf-8 -*-
"""pyRevit Routes API for creating grids, loading families, and managing levels."""

import clr
import os
import math
import tempfile
from pyrevit import routes
from pyrevit import revit, DB
from Autodesk.Revit.DB import (
    FilteredElementCollector, Level, ViewPlan, ElementId,
    Transaction, IFailuresPreprocessor, FailureProcessingResult,
    FailureSeverity, FailureResolutionType, ElementLevelFilter,
    DatumExtentType, DatumEnds, View, ViewType, ViewFamilyType,
    FormatOptions, UnitTypeId, SpecTypeId,
    Family, FamilySymbol, SetComparisonResult, IntersectionResultArray,
    CurveArray, CurveArrArray, SketchPlane,
    IFamilyLoadOptions, FamilySource, ElementTransformUtils,
    SaveAsOptions, Options, UV,
    DirectShape, GeometryCreationUtilities, CurveLoop, Line, XYZ,
    BuiltInCategory, ReferencePlane,
)
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI import UIApplication
from System.Collections.Generic import List

api = routes.API("grid-api")

# ------------------------------------------------------------------
# Unit conversion
# ------------------------------------------------------------------
FT_TO_M = 0.3048
M_TO_FT = 3.28084


# ------------------------------------------------------------------
# Safety net: dismiss ANY Revit dialog that pops up during Routes
# ------------------------------------------------------------------
def _on_dialog(sender, args):
    """Dismiss every Revit dialog automatically so Routes never blocks."""
    try:
        args.OverrideResult(1)  # 1 = OK / Close
    except Exception:
        pass


_dialog_handler_registered = False


def _ensure_dialog_handler():
    """Register the DialogBoxShowing handler once."""
    global _dialog_handler_registered
    if not _dialog_handler_registered:
        try:
            uiapp = revit.HOST_APP.uiapp
            if uiapp is not None:
                uiapp.DialogBoxShowing += _on_dialog
                _dialog_handler_registered = True
        except Exception:
            pass


# Register on startup
_ensure_dialog_handler()


# ------------------------------------------------------------------
# IFailuresPreprocessor: handles BOTH Warnings AND Errors
# ------------------------------------------------------------------
class LevelDeleteFailureHandler(IFailuresPreprocessor):
    """Handles both Warning and Error severity failures.

    The original WarningSwallower only called DeleteWarning() which throws
    ArgumentException on Error-severity failures. doc.Delete(Level) generates
    Error-severity failures (not warnings) when views are associated.

    Fix: use ResolveFailure() for errors + ProceedWithCommit.
    """

    def PreprocessFailures(self, failuresAccessor):
        resolved_errors = False

        for fail in failuresAccessor.GetFailureMessages():
            severity = fail.GetSeverity()

            if severity == FailureSeverity.Warning:
                # Warnings: can be deleted directly
                failuresAccessor.DeleteWarning(fail)

            elif severity == FailureSeverity.Error:
                # Errors: NEVER use DeleteWarning(), use ResolveFailure()
                if fail.HasResolutions():
                    if fail.HasResolutionOfType(FailureResolutionType.DetachElements):
                        fail.SetCurrentResolutionType(
                            FailureResolutionType.DetachElements)
                    elif fail.HasResolutionOfType(FailureResolutionType.DeleteElements):
                        fail.SetCurrentResolutionType(
                            FailureResolutionType.DeleteElements)
                    failuresAccessor.ResolveFailure(fail)
                    resolved_errors = True

        # CRITICAL: ProceedWithCommit if we resolved errors, Continue if only warnings
        if resolved_errors:
            return FailureProcessingResult.ProceedWithCommit
        return FailureProcessingResult.Continue


def _run_transaction(doc, name, action):
    """Run a Revit transaction with full failure handling."""
    t = Transaction(doc, name)
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(LevelDeleteFailureHandler())
    opts.SetForcedModalHandling(False)
    opts.SetClearAfterRollback(True)
    t.SetFailureHandlingOptions(opts)

    t.Start()
    try:
        action()
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise


# ------------------------------------------------------------------
# Grids
# ------------------------------------------------------------------

@api.route("/create_grids/", methods=["POST"])
def create_grids(doc, request):
    """Receive grid data from the external GUI and create grids in Revit."""
    data = request.data
    grids_x = data.get("grids_x", [])
    grids_y = data.get("grids_y", [])
    extent = data.get("extent", 5.0)

    created = [0]

    def do_create():
        from Autodesk.Revit.DB import ReferenceArray

        all_x = [g["x"] for g in grids_x]
        all_y = [g["y"] for g in grids_y]

        x_min = min(all_x) if all_x else 0
        x_max = max(all_x) if all_x else 0
        y_min = min(all_y) if all_y else 0
        y_max = max(all_y) if all_y else 0

        v_grids = []  # vertical grids (sorted by X)
        h_grids = []  # horizontal grids (sorted by Y)

        for g in grids_x:
            x = g["x"] * M_TO_FT
            y0 = (y_min - extent) * M_TO_FT
            y1 = (y_max + extent) * M_TO_FT
            line = DB.Line.CreateBound(
                DB.XYZ(x, y0, 0),
                DB.XYZ(x, y1, 0),
            )
            grid = DB.Grid.Create(doc, line)
            grid.Name = g["name"]
            v_grids.append(grid)
            created[0] += 1

        for g in grids_y:
            y = g["y"] * M_TO_FT
            x0 = (x_min - extent) * M_TO_FT
            x1 = (x_max + extent) * M_TO_FT
            line = DB.Line.CreateBound(
                DB.XYZ(x0, y, 0),
                DB.XYZ(x1, y, 0),
            )
            grid = DB.Grid.Create(doc, line)
            grid.Name = g["name"]
            h_grids.append(grid)
            created[0] += 1

    _run_transaction(doc, "Create Grids from GUI", do_create)

    return routes.make_response(
        data={"success": True, "created": created[0]},
    )


# ------------------------------------------------------------------
# Families
# ------------------------------------------------------------------

@api.route("/load_families/", methods=["POST"])
def load_families(doc, request):
    """Load .rfa family files into the current Revit document."""
    data = request.data
    families = data.get("families", [])

    loaded = [0]
    failed = [0]

    def do_load():
        for path in families:
            try:
                family_ref = clr.Reference[DB.Family]()
                success = doc.LoadFamily(path, family_ref)
                if success:
                    loaded[0] += 1
                else:
                    loaded[0] += 1
            except Exception:
                failed[0] += 1

    _run_transaction(doc, "Load Families from GUI", do_load)

    return routes.make_response(
        data={"success": True, "loaded": loaded[0], "failed": failed[0]},
    )


# ------------------------------------------------------------------
# Level alignment helper (Model extents approach)
# ------------------------------------------------------------------

def _classify_grids(doc):
    """Classify grids by orientation using Grid.Curve (plan-view curve).
    Returns x_positions (grids running in Y) and y_positions (grids running in X)."""
    grids = list(FilteredElementCollector(doc).OfClass(DB.Grid).ToElements())
    x_positions = []
    y_positions = []
    for grid in grids:
        curve = grid.Curve
        p0 = curve.GetEndPoint(0)
        p1 = curve.GetEndPoint(1)
        dx = abs(p1.X - p0.X)
        dy = abs(p1.Y - p0.Y)
        if dy > dx:
            x_positions.append((p0.X + p1.X) / 2.0)
        else:
            y_positions.append((p0.Y + p1.Y) / 2.0)
    return x_positions, y_positions


def _get_elevation_views_by_axis(doc):
    """Get elevation views grouped by horizontal axis (X or Y)."""
    all_views = list(FilteredElementCollector(doc).OfClass(View).ToElements())
    result = {"X": [], "Y": []}
    for v in all_views:
        try:
            if v.ViewType != ViewType.Elevation:
                continue
            if v.IsTemplate:
                continue
            rd = v.RightDirection
            if abs(rd.X) > abs(rd.Y):
                result["X"].append(v)
            else:
                result["Y"].append(v)
        except Exception:
            pass
    return result


def _align_levels_and_grids(doc):
    """Align level lines to match grid range, and extend grids
    so bubbles appear above the highest level.
    Does NOT use Maximize3DExtents on grids."""
    x_positions, y_positions = _classify_grids(doc)
    if not x_positions and not y_positions:
        return

    padding = 3.0  # feet (~1m) beyond outermost grids

    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not levels:
        return

    grids = list(FilteredElementCollector(doc).OfClass(DB.Grid).ToElements())

    # Z range for grid extents (bubbles above top level)
    elevations = [lv.Elevation for lv in levels]
    max_elev = max(elevations)
    min_elev = min(elevations)
    grid_z_top = max_elev + 8.0  # ~2.4m above top level for bubble

    views_by_axis = _get_elevation_views_by_axis(doc)

    def do_align():
        doc.Regenerate()

        # --- Part 1: Align level lines with grid range ---
        for axis in ["X", "Y"]:
            views = views_by_axis.get(axis, [])
            if not views:
                continue

            if axis == "X" and x_positions:
                target_min = min(x_positions) - padding
                target_max = max(x_positions) + padding
            elif axis == "Y" and y_positions:
                target_min = min(y_positions) - padding
                target_max = max(y_positions) + padding
            else:
                continue

            view = views[0]

            for lv in levels:
                try:
                    if not lv.CanBeVisibleInView(view):
                        continue
                    curves = lv.GetCurvesInView(DatumExtentType.Model, view)
                    if curves.Count == 0:
                        continue
                    c = curves[0]
                    pt0 = c.GetEndPoint(0)
                    if axis == "X":
                        new_line = DB.Line.CreateBound(
                            DB.XYZ(target_min, pt0.Y, pt0.Z),
                            DB.XYZ(target_max, pt0.Y, pt0.Z))
                    else:
                        new_line = DB.Line.CreateBound(
                            DB.XYZ(pt0.X, target_min, pt0.Z),
                            DB.XYZ(pt0.X, target_max, pt0.Z))
                    lv.SetCurveInView(DatumExtentType.Model, view, new_line)
                except Exception:
                    pass
            doc.Regenerate()

        # --- Part 2: Extend grid lines so bubbles are above top level ---
        # Grids are vertical in elevation views. Only change the Z (top)
        # to be above the highest level. Keep existing bottom Z.
        for axis in ["X", "Y"]:
            views = views_by_axis.get(axis, [])
            if not views:
                continue
            view = views[0]

            for g in grids:
                try:
                    if not g.CanBeVisibleInView(view):
                        continue
                    curves = g.GetCurvesInView(DatumExtentType.Model, view)
                    if curves.Count == 0:
                        continue
                    c = curves[0]
                    pt0 = c.GetEndPoint(0)
                    pt1 = c.GetEndPoint(1)

                    # Determine which end is top and which is bottom
                    if pt0.Z >= pt1.Z:
                        top_pt = pt0
                        bot_pt = pt1
                        # Only extend upward if current top is below target
                        if top_pt.Z < grid_z_top:
                            new_top = DB.XYZ(top_pt.X, top_pt.Y, grid_z_top)
                            new_line = DB.Line.CreateBound(new_top, bot_pt)
                            g.SetCurveInView(DatumExtentType.Model, view, new_line)
                    else:
                        top_pt = pt1
                        bot_pt = pt0
                        if top_pt.Z < grid_z_top:
                            new_top = DB.XYZ(top_pt.X, top_pt.Y, grid_z_top)
                            new_line = DB.Line.CreateBound(bot_pt, new_top)
                            g.SetCurveInView(DatumExtentType.Model, view, new_line)
                except Exception:
                    pass
            doc.Regenerate()

    _run_transaction(doc, "Align levels and grids", do_align)


# ------------------------------------------------------------------
# Grid Dimensions (Cotas)
# ------------------------------------------------------------------

@api.route("/create_grid_dimensions/", methods=["POST"])
def create_grid_dimensions(doc, request):
    """Create dimension chains between grid axes.
    Horizontal dims along bottom edge, vertical dims along left edge."""
    _ensure_dialog_handler()
    from Autodesk.Revit.DB import ReferenceArray, Dimension

    try:
        grids = list(FilteredElementCollector(doc).OfClass(DB.Grid).ToElements())
        if len(grids) < 2:
            return routes.make_response(
                status=400,
                data={"success": False, "error": "Se necesitan al menos 2 ejes."})

        # Separate grids by orientation
        group_h = []  # horizontal (running in X)
        group_v = []  # vertical (running in Y)
        for g in grids:
            curve = g.Curve
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            dx = abs(p1.X - p0.X)
            dy = abs(p1.Y - p0.Y)
            if dx >= dy:
                group_h.append(g)
            else:
                group_v.append(g)

        group_h.sort(key=lambda g: (g.Curve.GetEndPoint(0).Y + g.Curve.GetEndPoint(1).Y) / 2.0)
        group_v.sort(key=lambda g: (g.Curve.GetEndPoint(0).X + g.Curve.GetEndPoint(1).X) / 2.0)

        # Find a plan view to place dimensions
        plan_view = None
        for v in FilteredElementCollector(doc).OfClass(ViewPlan):
            if not v.IsTemplate:
                try:
                    if v.GenLevel is not None:
                        plan_view = v
                        break
                except Exception:
                    pass
        if plan_view is None:
            return routes.make_response(
                status=400,
                data={"success": False, "error": "No se encontro vista en planta."})

        dims_created = [0]
        offset_ft = 3.0  # 3 feet offset from grid edge for dimension line

        def do_dims():
            # ── HORIZONTAL DIMENSIONS (between vertical grids, along bottom) ──
            if len(group_v) >= 2:
                ref_array = ReferenceArray()
                for gv in group_v:
                    ref_array.Append(DB.Reference(gv))

                # Dimension line: horizontal, below the lowest horizontal grid
                if group_h:
                    min_y = min((g.Curve.GetEndPoint(0).Y + g.Curve.GetEndPoint(1).Y) / 2.0
                                for g in group_h)
                else:
                    min_y = 0
                y_dim = min_y - offset_ft

                avg_x0 = (group_v[0].Curve.GetEndPoint(0).X + group_v[0].Curve.GetEndPoint(1).X) / 2.0
                avg_x1 = (group_v[-1].Curve.GetEndPoint(0).X + group_v[-1].Curve.GetEndPoint(1).X) / 2.0
                dim_line = Line.CreateBound(
                    XYZ(avg_x0, y_dim, 0),
                    XYZ(avg_x1, y_dim, 0))

                try:
                    doc.Create.NewDimension(plan_view, dim_line, ref_array)
                    dims_created[0] += 1
                except Exception:
                    pass

            # ── VERTICAL DIMENSIONS (between horizontal grids, along left) ──
            if len(group_h) >= 2:
                ref_array = ReferenceArray()
                for gh in group_h:
                    ref_array.Append(DB.Reference(gh))

                # Dimension line: vertical, left of the leftmost vertical grid
                if group_v:
                    min_x = min((g.Curve.GetEndPoint(0).X + g.Curve.GetEndPoint(1).X) / 2.0
                                for g in group_v)
                else:
                    min_x = 0
                x_dim = min_x - offset_ft

                avg_y0 = (group_h[0].Curve.GetEndPoint(0).Y + group_h[0].Curve.GetEndPoint(1).Y) / 2.0
                avg_y1 = (group_h[-1].Curve.GetEndPoint(0).Y + group_h[-1].Curve.GetEndPoint(1).Y) / 2.0
                dim_line = Line.CreateBound(
                    XYZ(x_dim, avg_y0, 0),
                    XYZ(x_dim, avg_y1, 0))

                try:
                    doc.Create.NewDimension(plan_view, dim_line, ref_array)
                    dims_created[0] += 1
                except Exception:
                    pass

        _run_transaction(doc, "Create grid dimensions", do_dims)

        return routes.make_response(
            data={"success": True, "dimensions_created": dims_created[0]})

    except Exception as exc:
        return routes.make_response(
            status=500,
            data={"success": False, "error": str(exc)})


# ------------------------------------------------------------------
# Levels
# ------------------------------------------------------------------

@api.route("/get_levels/", methods=["GET"])
def get_levels(doc, request):
    """Return all levels in the current document."""
    collector = FilteredElementCollector(doc).OfClass(Level)
    levels = []
    for lv in collector:
        levels.append({
            "name": lv.Name,
            "elevation": round(lv.Elevation * FT_TO_M, 4),
        })
    levels.sort(key=lambda x: x["elevation"])
    return routes.make_response(
        data={"levels": levels},
    )


@api.route("/set_levels/", methods=["POST"])
def set_levels(doc, request):
    """Create or update levels. If replace=True, delete old levels first."""
    _ensure_dialog_handler()

    data = request.data
    levels_data = data.get("levels", [])
    replace = data.get("replace", True)

    deleted_names = []
    created_names = []
    updated_names = []
    skipped = []

    try:
        # Materialize collectors BEFORE any mutations
        collector = FilteredElementCollector(doc).OfClass(Level)
        all_levels = list(collector)
        existing = {}
        for lv in all_levels:
            existing[lv.Name] = lv

        if replace:
            new_names = set(item["name"] for item in levels_data)

            # Find floor plan ViewFamilyType for creating ViewPlans
            vft_collector = FilteredElementCollector(doc).OfClass(ViewFamilyType)
            floor_plan_vft = None
            for vft in vft_collector:
                if vft.ViewFamily == DB.ViewFamily.FloorPlan:
                    floor_plan_vft = vft
                    break

            # --- Transaction 1: Create/update levels + create ViewPlans ---
            def do_create_update():
                for lv_data in levels_data:
                    name = lv_data["name"]
                    elevation_ft = lv_data["elevation"] * M_TO_FT
                    if name in existing:
                        existing[name].Elevation = elevation_ft
                        updated_names.append(name)
                    else:
                        new_level = Level.Create(doc, elevation_ft)
                        new_level.Name = name
                        created_names.append(name)
                        # Create a floor plan view for the new level
                        if floor_plan_vft is not None:
                            try:
                                ViewPlan.Create(doc, floor_plan_vft.Id, new_level.Id)
                            except Exception:
                                pass

            _run_transaction(doc, "Create new levels", do_create_update)

            # --- Determine which old levels to delete ---
            old_levels = {}
            for name, lv in existing.items():
                if name not in new_names:
                    old_levels[name] = lv

            if old_levels:
                # Collect ALL ids to delete in one batch:
                # ViewPlans, hosted elements, and levels themselves
                ids_to_delete = List[ElementId]()
                active_view_id = doc.ActiveView.Id.IntegerValue

                for name, lv in old_levels.items():
                    level_id = lv.Id

                    # Collect ViewPlans associated with this level
                    view_collector = FilteredElementCollector(doc).OfClass(ViewPlan)
                    for view in list(view_collector):
                        if view.GenLevel is not None:
                            if view.GenLevel.Id.IntegerValue == level_id.IntegerValue:
                                if view.Id.IntegerValue != active_view_id:
                                    ids_to_delete.Add(view.Id)

                    # Collect elements hosted on this level
                    try:
                        level_filter = ElementLevelFilter(level_id)
                        hosted = FilteredElementCollector(doc).WherePasses(level_filter).ToElementIds()
                        for eid in hosted:
                            ids_to_delete.Add(eid)
                    except Exception:
                        pass

                    # Add the level itself
                    ids_to_delete.Add(level_id)

                # --- Transaction 2: Batch delete everything at once ---
                def do_batch_delete():
                    doc.Delete(ids_to_delete)

                try:
                    _run_transaction(doc, "Delete old levels", do_batch_delete)
                    for name in old_levels:
                        deleted_names.append(name)
                except Exception:
                    for name in old_levels:
                        skipped.append(name)
        else:
            # Find floor plan ViewFamilyType
            vft_collector = FilteredElementCollector(doc).OfClass(ViewFamilyType)
            floor_plan_vft = None
            for vft in vft_collector:
                if vft.ViewFamily == DB.ViewFamily.FloorPlan:
                    floor_plan_vft = vft
                    break

            # Just create/update without deleting
            def do_set():
                for lv_data in levels_data:
                    name = lv_data["name"]
                    elevation_ft = lv_data["elevation"] * M_TO_FT
                    if name in existing:
                        existing[name].Elevation = elevation_ft
                        updated_names.append(name)
                    else:
                        new_level = Level.Create(doc, elevation_ft)
                        new_level.Name = name
                        created_names.append(name)
                        if floor_plan_vft is not None:
                            try:
                                ViewPlan.Create(doc, floor_plan_vft.Id, new_level.Id)
                            except Exception:
                                pass

            _run_transaction(doc, "Set levels", do_set)

    except Exception as exc:
        return routes.make_response(
            status=500,
            data={"success": False, "error": str(exc)},
        )

    # Align level lines with grids and extend grid bubbles above top level
    try:
        _align_levels_and_grids(doc)
    except Exception:
        pass

    # Set units to meters
    try:
        def do_set_units():
            units = doc.GetUnits()
            fmt = FormatOptions(UnitTypeId.Meters)
            fmt.Accuracy = 0.01
            units.SetFormatOptions(SpecTypeId.Length, fmt)
            doc.SetUnits(units)
        _run_transaction(doc, "Set units to meters", do_set_units)
    except Exception:
        pass

    # ── AUTO-CREATE GRID DIMENSIONS in ALL plan views ──
    try:
        from Autodesk.Revit.DB import ReferenceArray

        grids = list(FilteredElementCollector(doc).OfClass(DB.Grid).ToElements())
        g_v = []  # vertical grids (running in Y)
        g_h = []  # horizontal grids (running in X)
        for g in grids:
            curve = g.Curve
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            if abs(p1.Y - p0.Y) > abs(p1.X - p0.X):
                g_v.append(g)
            else:
                g_h.append(g)

        g_v.sort(key=lambda g: (g.Curve.GetEndPoint(0).X + g.Curve.GetEndPoint(1).X) / 2.0)
        g_h.sort(key=lambda g: (g.Curve.GetEndPoint(0).Y + g.Curve.GetEndPoint(1).Y) / 2.0)

        if g_v or g_h:
            # Get grid extents for offset
            all_x = [(g.Curve.GetEndPoint(0).X + g.Curve.GetEndPoint(1).X) / 2.0 for g in g_v] if g_v else [0]
            all_y = [(g.Curve.GetEndPoint(0).Y + g.Curve.GetEndPoint(1).Y) / 2.0 for g in g_h] if g_h else [0]
            x_max = max(all_x)
            y_max = max(all_y)
            # Grid extent (end of grid lines)
            if g_v:
                y_top = max(g_v[0].Curve.GetEndPoint(0).Y, g_v[0].Curve.GetEndPoint(1).Y)
            else:
                y_top = y_max + 16.4  # 5m default
            if g_h:
                x_right = max(g_h[0].Curve.GetEndPoint(0).X, g_h[0].Curve.GetEndPoint(1).X)
            else:
                x_right = x_max + 16.4

            offset_ft = 6.0  # ~2m offset from grid bubble

            # Collect ALL plan views
            plan_views = []
            for v in FilteredElementCollector(doc).OfClass(ViewPlan):
                if not v.IsTemplate:
                    try:
                        if v.GenLevel is not None:
                            plan_views.append(v)
                    except Exception:
                        pass

            dim_dbg = []

            def do_create_dims():
                dim_dbg.append("views=%d g_v=%d g_h=%d" % (len(plan_views), len(g_v), len(g_h)))
                for pv in plan_views:
                    dim_dbg.append("view: %s" % pv.Name)
                    # Horizontal dims (A,B,C,D) — ABOVE top grid
                    if len(g_v) >= 2:
                        try:
                            ref_arr = ReferenceArray()
                            for gv in g_v:
                                ref_arr.Append(DB.Reference(gv))
                            y_dim = y_top + offset_ft
                            x0 = all_x[0]
                            x1 = all_x[-1]
                            dim_line = Line.CreateBound(
                                XYZ(x0, y_dim, 0), XYZ(x1, y_dim, 0))
                            d = doc.Create.NewDimension(pv, dim_line, ref_arr)
                            dim_dbg.append("  H-dim OK id=%s" % str(d.Id.IntegerValue))
                        except Exception as e:
                            dim_dbg.append("  H-dim ERR: %s" % str(e))

                    # Vertical dims (1,2,3) — RIGHT of rightmost grid
                    if len(g_h) >= 2:
                        try:
                            ref_arr = ReferenceArray()
                            for gh in g_h:
                                ref_arr.Append(DB.Reference(gh))
                            x_dim = x_right + offset_ft
                            y0 = all_y[0]
                            y1 = all_y[-1]
                            dim_line = Line.CreateBound(
                                XYZ(x_dim, y0, 0), XYZ(x_dim, y1, 0))
                            d = doc.Create.NewDimension(pv, dim_line, ref_arr)
                            dim_dbg.append("  V-dim OK id=%s" % str(d.Id.IntegerValue))
                        except Exception as e:
                            dim_dbg.append("  V-dim ERR: %s" % str(e))

            _run_transaction(doc, "Create grid dimensions", do_create_dims)

            # Write debug
            try:
                f = open(os.path.join(os.path.expanduser("~"), "Desktop", "dim_debug.txt"), "w")
                f.write("\n".join(dim_dbg))
                f.close()
            except Exception:
                pass
    except Exception as ex:
        try:
            f = open(os.path.join(os.path.expanduser("~"), "Desktop", "dim_debug.txt"), "w")
            f.write("OUTER ERROR: %s" % str(ex))
            f.close()
        except Exception:
            pass

    return routes.make_response(
        data={
            "success": True,
            "created": len(created_names),
            "updated": len(updated_names),
            "deleted": len(deleted_names),
            "skipped": skipped,
        },
    )


@api.route("/align_levels/", methods=["POST"])
def align_levels(doc, request):
    """Align all level lines with grid extents in elevation views."""
    _ensure_dialog_handler()
    try:
        _align_levels_and_grids(doc)
        return routes.make_response(data={"success": True})
    except Exception as exc:
        return routes.make_response(
            status=500,
            data={"success": False, "error": str(exc)},
        )


@api.route("/set_units_meters/", methods=["POST"])
def set_units_meters(doc, request):
    """Set project length units to meters."""
    def do_set_units():
        units = doc.GetUnits()
        fmt = FormatOptions(UnitTypeId.Meters)
        fmt.Accuracy = 0.01
        units.SetFormatOptions(SpecTypeId.Length, fmt)
        doc.SetUnits(units)

    try:
        _run_transaction(doc, "Set units to meters", do_set_units)
        return routes.make_response(data={"success": True})
    except Exception as exc:
        return routes.make_response(
            status=500,
            data={"success": False, "error": str(exc)},
        )


# ------------------------------------------------------------------
# Foundations: IFamilyLoadOptions for reloading families
# ------------------------------------------------------------------
class _FamilyLoadOption(IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = True
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        source.Value = FamilySource.Family
        overwriteParameterValues.Value = True
        return True


# ------------------------------------------------------------------
# Foundations: helpers
# ------------------------------------------------------------------

def _find_footing_family(doc, app):
    """Find or load Footing-Rectangular family. Returns Family object."""
    # Check if already loaded
    collector = FilteredElementCollector(doc).OfClass(Family)
    for fam in collector:
        try:
            if fam.Name == "Footing-Rectangular":
                return fam
        except Exception:
            pass

    # Search in Revit library paths
    search_paths = [
        r"C:\ProgramData\Autodesk\RVT 2024\Libraries\US Imperial\Structural Foundations",
        r"C:\ProgramData\Autodesk\RVT 2024\Libraries\US Metric\Structural Foundations",
        r"C:\ProgramData\Autodesk\RVT 2024\Libraries\UK\Structural Foundations",
        r"C:\ProgramData\Autodesk\RVT 2024\Libraries\Spanish\Structural Foundations",
    ]

    family_path = None
    for base in search_paths:
        candidate = os.path.join(base, "Footing-Rectangular.rfa")
        if os.path.exists(candidate):
            family_path = candidate
            break

    # Recursive fallback search
    if family_path is None:
        lib_base = r"C:\ProgramData\Autodesk\RVT 2024\Libraries"
        if os.path.exists(lib_base):
            for root, dirs, files in os.walk(lib_base):
                for f in files:
                    if f.lower() == "footing-rectangular.rfa":
                        family_path = os.path.join(root, f)
                        break
                if family_path:
                    break

    if family_path is None:
        return None

    family_ref = clr.Reference[Family]()
    success = doc.LoadFamily(family_path, _FamilyLoadOption(), family_ref)
    if success:
        return family_ref.Value

    # If returns False, already loaded
    collector2 = FilteredElementCollector(doc).OfClass(Family)
    for fam in collector2:
        try:
            if fam.Name == "Footing-Rectangular":
                return fam
        except Exception:
            pass
    return None


def _create_footing_family_from_template(doc, app, name, width_ft, length_ft, height_ft):
    """Create a parametric foundation family from template.
    Uses NewAlignment to link extrusion faces to Reference Planes
    so Width/Length/Thickness parameters control the geometry.
    Returns the Family object loaded into doc."""
    from Autodesk.Revit.DB import (
        Plane, PlanarFace, Solid, View
    )

    # Find template
    template_file = None
    try:
        tpl_dir = app.FamilyTemplatePath
        for root, dirs, files in os.walk(tpl_dir):
            for f in files:
                if "structural foundation" in f.lower() and f.lower().endswith(".rft"):
                    template_file = os.path.join(root, f)
                    break
            if template_file:
                break
    except Exception:
        pass
    if template_file is None:
        template_base = r"C:\ProgramData\Autodesk\RVT 2024\Family Templates"
        for root, dirs, files in os.walk(template_base):
            for f in files:
                if "structural foundation" in f.lower() and f.lower().endswith(".rft"):
                    template_file = os.path.join(root, f)
                    break
            if template_file:
                break

    if template_file is None:
        raise Exception("No se encontro plantilla de Structural Foundation (.rft)")

    family_doc = app.NewFamilyDocument(template_file)

    def _find_elem_fd(cls, name):
        for e in FilteredElementCollector(family_doc).OfClass(cls):
            if e.Name == name:
                return e
        return None

    def _find_face_fd(ext, normal):
        opt = Options()
        opt.ComputeReferences = True
        geom = ext.get_Geometry(opt)
        for g in geom:
            if isinstance(g, Solid) and g.Faces.Size > 0:
                for face in g.Faces:
                    if isinstance(face, PlanarFace):
                        if face.FaceNormal.IsAlmostEqualTo(normal):
                            return face
        return None

    # Read template's default Width/Length to position extrusion correctly
    fm = family_doc.FamilyManager

    t_fam = Transaction(family_doc, "Create Foundation Geometry")
    t_fam.Start()
    try:
        if fm.CurrentType is None:
            fm.NewType("Default")

        # Read current Width/Length from template params
        param_w = None
        param_l = None
        param_t = None
        for fp in fm.Parameters:
            pn = fp.Definition.Name
            if pn in ("Width", "Ancho", "w") and param_w is None:
                param_w = fp
            elif pn in ("Length", "Largo", "Longitud", "l") and param_l is None:
                param_l = fp
            elif pn in ("Foundation Thickness", "Espesor", "Thickness") and param_t is None:
                param_t = fp

        # Use template default values for extrusion (must match ref planes)
        w_val = fm.CurrentType.AsDouble(param_w) if param_w else width_ft
        l_val = fm.CurrentType.AsDouble(param_l) if param_l else length_ft
        t_val = fm.CurrentType.AsDouble(param_t) if param_t else height_ft

        if w_val <= 0:
            w_val = width_ft
        if l_val <= 0:
            l_val = length_ft
        if t_val <= 0:
            t_val = height_ft

        hw = w_val / 2.0
        hl = l_val / 2.0

        # Find SketchPlane
        sketch_plane = None
        for sp in FilteredElementCollector(family_doc).OfClass(SketchPlane):
            if "Ref. Level" in sp.Name or "Ref Level" in sp.Name:
                sketch_plane = sp
                break
        if sketch_plane is None:
            sketch_plane = SketchPlane.Create(
                family_doc,
                Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, DB.XYZ.Zero))

        # Create rectangular profile matching ref plane positions
        p0 = DB.XYZ(-hw, -hl, 0.0)
        p1 = DB.XYZ(hw, -hl, 0.0)
        p2 = DB.XYZ(hw, hl, 0.0)
        p3 = DB.XYZ(-hw, hl, 0.0)

        ca = CurveArray()
        ca.Append(DB.Line.CreateBound(p0, p1))
        ca.Append(DB.Line.CreateBound(p1, p2))
        ca.Append(DB.Line.CreateBound(p2, p3))
        ca.Append(DB.Line.CreateBound(p3, p0))

        caa = CurveArrArray()
        caa.Append(ca)

        extrusion = family_doc.FamilyCreate.NewExtrusion(
            True, caa, sketch_plane, t_val)

        family_doc.Regenerate()

        # ── ALIGN 4 side faces to Reference Planes (parametric Width/Length) ──
        plan_view = None
        for v in FilteredElementCollector(family_doc).OfClass(ViewPlan):
            if not v.IsTemplate:
                plan_view = v
                break

        rp_right = _find_elem_fd(ReferencePlane, "Right")
        rp_left = _find_elem_fd(ReferencePlane, "Left")
        rp_front = _find_elem_fd(ReferencePlane, "Front")
        rp_back = _find_elem_fd(ReferencePlane, "Back")

        if plan_view:
            creator = family_doc.FamilyCreate

            face_r = _find_face_fd(extrusion, DB.XYZ(1, 0, 0))
            if face_r and rp_right:
                try:
                    creator.NewAlignment(plan_view, rp_right.GetReference(), face_r.Reference)
                except Exception:
                    pass

            face_l = _find_face_fd(extrusion, DB.XYZ(-1, 0, 0))
            if face_l and rp_left:
                try:
                    creator.NewAlignment(plan_view, rp_left.GetReference(), face_l.Reference)
                except Exception:
                    pass

            face_f = _find_face_fd(extrusion, DB.XYZ(0, -1, 0))
            if face_f and rp_front:
                try:
                    creator.NewAlignment(plan_view, rp_front.GetReference(), face_f.Reference)
                except Exception:
                    pass

            face_b = _find_face_fd(extrusion, DB.XYZ(0, 1, 0))
            if face_b and rp_back:
                try:
                    creator.NewAlignment(plan_view, rp_back.GetReference(), face_b.Reference)
                except Exception:
                    pass

        # ── ALIGN top/bottom faces to levels (parametric Thickness) ──
        front_view = None
        for v in FilteredElementCollector(family_doc).OfClass(View):
            if not v.IsTemplate and not isinstance(v, ViewPlan):
                vn = v.Name.lower()
                if "front" in vn or "frente" in vn:
                    front_view = v
                    break
        # Fallback: any elevation view
        if front_view is None:
            for v in FilteredElementCollector(family_doc).OfClass(View):
                if not v.IsTemplate and not isinstance(v, ViewPlan):
                    front_view = v
                    break

        if front_view:
            # Foundation templates use "Ref. Level" for top
            ref_level = _find_elem_fd(Level, "Ref. Level")
            if ref_level is None:
                ref_level = _find_elem_fd(Level, "Ref Level")

            face_top = _find_face_fd(extrusion, DB.XYZ(0, 0, 1))
            if face_top and ref_level:
                try:
                    family_doc.FamilyCreate.NewAlignment(
                        front_view, ref_level.GetPlaneReference(), face_top.Reference)
                except Exception:
                    pass

        # Set desired Width/Length/Thickness
        if param_w:
            fm.Set(param_w, width_ft)
        if param_l:
            fm.Set(param_l, length_ft)
        if param_t:
            fm.Set(param_t, height_ft)

        family_doc.Regenerate()
        t_fam.Commit()
    except Exception:
        try:
            t_fam.RollBack()
        except Exception:
            pass
        family_doc.Close(False)
        raise

    # Save and load
    # Use the family NAME as the filename so each size gets its own .rfa
    rfa_path = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                            "Temp", "%s.rfa" % name)
    save_opts = SaveAsOptions()
    save_opts.OverwriteExistingFile = True
    family_doc.SaveAs(rfa_path, save_opts)
    family_doc.Close(False)

    # Load via doc.LoadFamily inside Transaction
    family_ref = clr.Reference[Family]()
    t_load = Transaction(doc, "Load Zapata")
    t_load.Start()
    try:
        ok = doc.LoadFamily(rfa_path, _FamilyLoadOption(), family_ref)
        t_load.Commit()
        if ok and family_ref.Value is not None:
            return family_ref.Value
    except Exception:
        try:
            t_load.RollBack()
        except Exception:
            pass

    # Fallback: find by category
    collector = FilteredElementCollector(doc).OfClass(Family)
    for fam in collector:
        try:
            cat = fam.FamilyCategory
            if cat is not None:
                if cat.Id.IntegerValue == int(DB.BuiltInCategory.OST_StructuralFoundation):
                    return fam
        except Exception:
            pass
    return None


def _get_or_create_footing_type(doc, family, type_name, width_mm, length_mm, thickness_mm):
    """Get or create a footing type with given dimensions (in mm).

    Since the foundation template only has 'Longitud' as editable param,
    we create a NEW family for each unique size instead of duplicating types."""
    # Check if type already exists
    for sym_id in family.GetFamilySymbolIds():
        sym = doc.GetElement(sym_id)
        try:
            sym_name = sym.Name
        except Exception:
            sym_name = DB.Element.Name.GetValue(sym)
        if sym_name == type_name:
            if not sym.IsActive:
                sym.Activate()
                doc.Regenerate()
            return sym

    # Duplicate from first type
    first_id = list(family.GetFamilySymbolIds())[0]
    base_symbol = doc.GetElement(first_id)
    new_symbol = base_symbol.Duplicate(type_name)

    w_ft = width_mm / 304.8
    l_ft = length_mm / 304.8
    t_ft = thickness_mm / 304.8

    # Try setting params by name (works if template has them)
    for p in new_symbol.Parameters:
        try:
            pn = p.Definition.Name
            st = str(p.StorageType)
            if st == "Double" and not p.IsReadOnly:
                pnl = pn.lower()
                if pnl in ("width", "ancho", "w", "b"):
                    p.Set(w_ft)
                elif pnl in ("length", "largo", "longitud", "l"):
                    p.Set(l_ft)
                elif "thick" in pnl or "espesor" in pnl:
                    p.Set(t_ft)
        except Exception:
            pass

    if not new_symbol.IsActive:
        new_symbol.Activate()
        doc.Regenerate()

    return new_symbol


def _get_grid_intersections(doc):
    """Compute grid intersections and classify as central/esquinera/lindero."""
    grids = list(FilteredElementCollector(doc).OfClass(DB.Grid).ToElements())
    if len(grids) < 2:
        return []

    # Separate by orientation
    group_h = []  # horizontal (running in X direction)
    group_v = []  # vertical (running in Y direction)

    for g in grids:
        curve = g.Curve
        p0 = curve.GetEndPoint(0)
        p1 = curve.GetEndPoint(1)
        dx = abs(p1.X - p0.X)
        dy = abs(p1.Y - p0.Y)
        if dx >= dy:
            group_h.append(g)
        else:
            group_v.append(g)

    # Sort: horizontal by Y, vertical by X
    group_h.sort(key=lambda g: (g.Curve.GetEndPoint(0).Y + g.Curve.GetEndPoint(1).Y) / 2.0)
    group_v.sort(key=lambda g: (g.Curve.GetEndPoint(0).X + g.Curve.GetEndPoint(1).X) / 2.0)

    count_h = len(group_h)
    count_v = len(group_v)
    intersections = []

    for i_h, gh in enumerate(group_h):
        for i_v, gv in enumerate(group_v):
            try:
                results = clr.Reference[IntersectionResultArray]()
                result = gh.Curve.Intersect(gv.Curve, results)

                if result == SetComparisonResult.Overlap:
                    int_array = results.Value
                    if int_array is not None and int_array.Size > 0:
                        point = int_array.get_Item(0).XYZPoint

                        is_h_edge = (i_h == 0 or i_h == count_h - 1)
                        is_v_edge = (i_v == 0 or i_v == count_v - 1)

                        if is_h_edge and is_v_edge:
                            category = "esquinera"
                        elif is_h_edge or is_v_edge:
                            category = "lindero"
                        else:
                            category = "central"

                        try:
                            name_h = gh.Name
                        except Exception:
                            name_h = DB.Element.Name.GetValue(gh)
                        try:
                            name_v = gv.Name
                        except Exception:
                            name_v = DB.Element.Name.GetValue(gv)

                        # Direction toward center: computed after all intersections
                        # (will be filled in below)
                        sign_x = 0
                        sign_y = 0

                        # edge_type: which edge this lindero is on
                        # "h" = horizontal edge (top/bottom, axes 1/3) → shift in Y
                        # "v" = vertical edge (left/right, axes A/D) → shift in X
                        # "both" = corner (esquinera)
                        if is_h_edge and is_v_edge:
                            edge_type = "both"
                        elif is_h_edge:
                            edge_type = "h"  # on top or bottom edge
                        elif is_v_edge:
                            edge_type = "v"  # on left or right edge
                        else:
                            edge_type = "none"

                        intersections.append({
                            "point": point,
                            "category": category,
                            "grid_h": name_h,
                            "grid_v": name_v,
                            "sign_x": sign_x,
                            "sign_y": sign_y,
                            "edge_type": edge_type,
                        })
            except Exception:
                pass

    # Compute centroid and assign sign_x/sign_y toward center
    if intersections:
        cx = sum(i["point"].X for i in intersections) / float(len(intersections))
        cy = sum(i["point"].Y for i in intersections) / float(len(intersections))
        for info in intersections:
            if info["category"] in ("esquinera", "lindero"):
                dx = cx - info["point"].X
                dy = cy - info["point"].Y
                # sign = direction toward center (+1 or -1)
                info["sign_x"] = 1 if dx > 0.01 else (-1 if dx < -0.01 else 0)
                info["sign_y"] = 1 if dy > 0.01 else (-1 if dy < -0.01 else 0)

    return intersections


def _get_lowest_level(doc):
    """Return the level with lowest elevation."""
    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not levels:
        return None
    levels.sort(key=lambda lv: lv.Elevation)
    return levels[0]


def _get_next_level_above(doc, base_level):
    """Return the level immediately above base_level, or None."""
    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    levels.sort(key=lambda lv: lv.Elevation)
    for lv in levels:
        if lv.Elevation > base_level.Elevation + 0.01:
            return lv
    return None


def _is_steel_family(name):
    """Return True if the family name suggests a steel/I-beam profile."""
    n = name.lower()
    steel_keywords = [
        "steel", "wide flange", "w-shape", "hss", "tube", "pipe",
        "angle", "channel", "tee", "z-shape", "c-shape", "l-shape",
        "acero", "perfil", "viga", " w ", "ipe ", "hea", "heb", "ipe",
        " uc", " ub", "uc ", "ub ", "-uc", "-ub",
        "universal column", "universal beam",
    ]
    return any(kw in n for kw in steel_keywords)


def _find_column_family(doc, app, w_mm=None, d_mm=None):
    """Find or create a CONCRETE rectangular structural column family.

    Revit 2024 does NOT pre-install library .rfa files (on-demand download),
    so we skip the library walk entirely to avoid picking up UC/UB steel profiles
    or wasting time on an empty folder.

    Strategy:
      1. Return a family already in the doc that has a concrete keyword and
         no steel keyword in its name.
      2. Create from the Metric Structural Column.rft template.
    """
    col_cat_id = int(DB.BuiltInCategory.OST_StructuralColumns)
    steel_kw = [
        "steel", "wide flange", "w-shape", "hss", "tube", "pipe",
        "angle", "channel", "tee", "acero", "ipe", "hea", "heb", "perfil",
        " uc", " ub", "uc ", "ub ", "-uc", "-ub",
        "universal column", "universal beam",
    ]
    concrete_kw = ["concrete", "concreto", "hormigon", "pedestal", "rectangular"]

    def _is_steel(name):
        n = name.lower()
        return any(kw in n for kw in steel_kw)

    def _is_concrete_col(name):
        n = name.lower()
        return any(kw in n for kw in concrete_kw)

    # 1. Prefer a concrete-keyword family already loaded in the doc
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            cat = fam.FamilyCategory
            if cat is None or cat.Id.IntegerValue != col_cat_id:
                continue
            if _is_concrete_col(fam.Name) and not _is_steel(fam.Name):
                return fam
        except Exception:
            pass

    # 2. Create from RFT template
    #    (Library walk skipped: Revit 2024 has no pre-installed .rfa files)
    return _create_column_family_from_template(doc, app, w_mm, d_mm)


def _create_column_family_from_template(doc, app, _col_create_w_mm=None, _col_create_d_mm=None):
    """Create a rectangular concrete structural column family from the RFT template.

    The template has NO geometry — only reference planes and parameters.
    We must create the extrusion with FamilyCreate.NewExtrusion().
    pyRevit Routes dispatches to main thread when handler declares 'doc',
    so doc.LoadFamily works here.
    """
    # ── 1. Find template ──
    template_file = None
    try:
        tpl_dir = app.FamilyTemplatePath
        for root, dirs, files in os.walk(tpl_dir):
            for f in files:
                if f.lower() == "metric structural column.rft":
                    template_file = os.path.join(root, f)
                    break
            if template_file:
                break
    except Exception:
        pass

    if template_file is None:
        p = r"C:\ProgramData\Autodesk\RVT 2024\Family Templates\English\Metric Structural Column.rft"
        if os.path.exists(p):
            template_file = p

    if template_file is None:
        raise Exception("Metric Structural Column.rft not found")

    # ── 2. Open family document from template ──
    family_doc = app.NewFamilyDocument(template_file)

    # ── 3. Create parametric extrusion with 6 alignments ──
    from Autodesk.Revit.DB import (
        Plane, PlanarFace, Solid, View
    )

    fm = family_doc.FamilyManager

    def _find_elem(fdoc, cls, name):
        for e in FilteredElementCollector(fdoc).OfClass(cls):
            if e.Name == name:
                return e
        return None

    def _find_face(ext, normal):
        opt = Options()
        opt.ComputeReferences = True
        geom = ext.get_Geometry(opt)
        for g in geom:
            if isinstance(g, Solid) and g.Faces.Size > 0:
                for face in g.Faces:
                    if isinstance(face, PlanarFace):
                        if face.FaceNormal.IsAlmostEqualTo(normal):
                            return face
        return None

    t_fam = Transaction(family_doc, "Create parametric column")
    t_fam.Start()
    try:
        # Ensure type exists
        if fm.CurrentType is None:
            fm.NewType("Default")

        # Read Width/Depth params — position extrusion to MATCH ref planes
        param_w = None
        param_d = None
        for fp in fm.Parameters:
            name = fp.Definition.Name
            if name in ("Width", "Ancho", "b", "w") and param_w is None:
                param_w = fp
            elif name in ("Depth", "Profundidad", "h", "d") and param_d is None:
                param_d = fp

        # Read current values from template (must match ref plane positions)
        w_val = fm.CurrentType.AsDouble(param_w) if param_w else 600.0 / 304.8
        d_val = fm.CurrentType.AsDouble(param_d) if param_d else 600.0 / 304.8
        hw = w_val / 2.0
        hd = d_val / 2.0

        # Find levels for height
        upper_lv = _find_elem(family_doc, Level, "Upper Ref Level")
        lower_lv = _find_elem(family_doc, Level, "Lower Ref. Level")
        if upper_lv and lower_lv:
            ext_height = upper_lv.Elevation - lower_lv.Elevation
        else:
            ext_height = 3000.0 / 304.8

        if ext_height <= 0:
            ext_height = 3000.0 / 304.8

        # Create sketch plane at Lower Ref. Level (Z=0)
        sketch_plane = SketchPlane.Create(
            family_doc,
            Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, DB.XYZ.Zero)
        )

        # Build rectangular profile matching ref plane positions
        p0 = DB.XYZ(-hw, -hd, 0.0)
        p1 = DB.XYZ(hw, -hd, 0.0)
        p2 = DB.XYZ(hw, hd, 0.0)
        p3 = DB.XYZ(-hw, hd, 0.0)

        ca = CurveArray()
        ca.Append(Line.CreateBound(p0, p1))
        ca.Append(Line.CreateBound(p1, p2))
        ca.Append(Line.CreateBound(p2, p3))
        ca.Append(Line.CreateBound(p3, p0))

        caa = CurveArrArray()
        caa.Append(ca)

        extrusion = family_doc.FamilyCreate.NewExtrusion(True, caa, sketch_plane, ext_height)

        # CRITICAL: regenerate so faces are available for alignment
        family_doc.Regenerate()

        # ── 4 SIDE ALIGNMENTS (plan view) ──
        plan_view = _find_elem(family_doc, ViewPlan, "Lower Ref. Level")

        rp_right = _find_elem(family_doc, ReferencePlane, "Right")
        rp_left = _find_elem(family_doc, ReferencePlane, "Left")
        rp_front = _find_elem(family_doc, ReferencePlane, "Front")
        rp_back = _find_elem(family_doc, ReferencePlane, "Back")

        if plan_view:
            creator = family_doc.FamilyCreate

            face_r = _find_face(extrusion, DB.XYZ(1, 0, 0))
            if face_r and rp_right:
                creator.NewAlignment(plan_view, rp_right.GetReference(), face_r.Reference)

            face_l = _find_face(extrusion, DB.XYZ(-1, 0, 0))
            if face_l and rp_left:
                creator.NewAlignment(plan_view, rp_left.GetReference(), face_l.Reference)

            face_f = _find_face(extrusion, DB.XYZ(0, -1, 0))
            if face_f and rp_front:
                creator.NewAlignment(plan_view, rp_front.GetReference(), face_f.Reference)

            face_b = _find_face(extrusion, DB.XYZ(0, 1, 0))
            if face_b and rp_back:
                creator.NewAlignment(plan_view, rp_back.GetReference(), face_b.Reference)

        # ── 2 VERTICAL ALIGNMENTS (elevation view) ──
        # Find elevation view — try multiple names (English/Spanish)
        front_view = None
        all_views = []
        for v in FilteredElementCollector(family_doc).OfClass(View):
            if not v.IsTemplate:
                all_views.append(v.Name)
                vn = v.Name.lower()
                if vn in ("front", "frente", "frontal", "alzado frontal"):
                    front_view = v
        # Fallback: first non-plan, non-template view
        if front_view is None:
            for v in FilteredElementCollector(family_doc).OfClass(View):
                if not v.IsTemplate and not isinstance(v, ViewPlan):
                    front_view = v
                    break

        _fam_dbg = []
        _fam_dbg.append("views=%s" % str(all_views))
        _fam_dbg.append("front_view=%s" % (front_view.Name if front_view else "NONE"))
        _fam_dbg.append("upper_lv=%s" % (upper_lv.Name if upper_lv else "NONE"))
        _fam_dbg.append("lower_lv=%s" % (lower_lv.Name if lower_lv else "NONE"))
        _fam_dbg.append("ext_height=%.3f ft" % ext_height)

        if front_view:
            face_top = _find_face(extrusion, DB.XYZ(0, 0, 1))
            face_bot = _find_face(extrusion, DB.XYZ(0, 0, -1))
            _fam_dbg.append("face_top=%s face_bot=%s" % (
                face_top is not None, face_bot is not None))

            if face_top and upper_lv:
                try:
                    family_doc.FamilyCreate.NewAlignment(
                        front_view, upper_lv.GetPlaneReference(), face_top.Reference)
                    _fam_dbg.append("align_top=OK")
                except Exception as ae:
                    _fam_dbg.append("align_top_ERR=%s" % str(ae))

            if face_bot and lower_lv:
                try:
                    family_doc.FamilyCreate.NewAlignment(
                        front_view, lower_lv.GetPlaneReference(), face_bot.Reference)
                    _fam_dbg.append("align_bot=OK")
                except Exception as ae:
                    _fam_dbg.append("align_bot_ERR=%s" % str(ae))

        # Write family debug to file
        try:
            fdbg_path = os.path.join(os.path.expanduser("~"), "Desktop", "family_debug.txt")
            f = open(fdbg_path, "w")
            f.write("\n".join(_fam_dbg))
            f.close()
        except Exception:
            pass

        # Now set desired Width/Depth
        w_ft = _col_create_w_mm / 304.8 if _col_create_w_mm else 400.0 / 304.8
        d_ft = _col_create_d_mm / 304.8 if _col_create_d_mm else 400.0 / 304.8
        if param_w:
            fm.Set(param_w, w_ft)
        if param_d:
            fm.Set(param_d, d_ft)

        family_doc.Regenerate()
        t_fam.Commit()
    except Exception:
        try:
            t_fam.RollBack()
        except Exception:
            pass
        family_doc.Close(False)
        raise

    # ── 4. SaveAs ──
    rfa_path = os.path.join(os.path.expanduser("~"), "AppData", "Local",
                            "Temp", "PedestalConcreto.rfa")
    save_opts = SaveAsOptions()
    save_opts.OverwriteExistingFile = True
    family_doc.SaveAs(rfa_path, save_opts)

    # ── 5. Load into project via file path inside Transaction ──
    #       Routes dispatches to main thread → doc.LoadFamily(path) works.
    family_doc.Close(False)

    family_ref = clr.Reference[Family]()
    t_load = Transaction(doc, "Load PedestalConcreto")
    t_load.Start()
    try:
        ok = doc.LoadFamily(rfa_path, _FamilyLoadOption(), family_ref)
        t_load.Commit()
        if ok and family_ref.Value is not None:
            return family_ref.Value
    except Exception:
        try:
            t_load.RollBack()
        except Exception:
            pass

    # Fallback: find by name
    for fam in FilteredElementCollector(doc).OfClass(Family):
        if fam.Name == "PedestalConcreto":
            return fam

    # Fallback: find any non-steel structural column
    col_cat_id = int(DB.BuiltInCategory.OST_StructuralColumns)
    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            cat = fam.FamilyCategory
            if cat is not None and cat.Id.IntegerValue == col_cat_id:
                if not _is_steel_family(fam.Name):
                    return fam
        except Exception:
            pass
    return None


def _get_or_create_column_type(doc, family, type_name, width_mm, depth_mm):
    """Get or create a column FamilySymbol with given dimensions (in mm).

    Must be called inside an open Transaction on doc.
    Parameters "b" (width) and "h" (depth) are type parameters — confirmed
    names for families created from Metric Structural Column.rft.
    """
    w_ft = width_mm / 304.8
    d_ft = depth_mm / 304.8

    # Check if type already exists
    for sym_id in family.GetFamilySymbolIds():
        sym = doc.GetElement(sym_id)
        try:
            sym_name = sym.Name
        except Exception:
            sym_name = DB.Element.Name.GetValue(sym)
        if sym_name == type_name:
            # Activate (required before first placement)
            if not sym.IsActive:
                sym.Activate()
                doc.Regenerate()
            return sym

    # Type does not exist → duplicate from first available symbol
    sym_ids = list(family.GetFamilySymbolIds())
    if not sym_ids:
        return None
    base_symbol = doc.GetElement(sym_ids[0])

    # Duplicate — FamilySymbol.Duplicate() confirmed in Revit 2024
    new_symbol = base_symbol.Duplicate(type_name)

    # Set Width and Depth — try English, Spanish, and shorthand names
    w_set = False
    for pname in ["Width", "Ancho", "Anchura", "b", "w"]:
        p = new_symbol.LookupParameter(pname)
        if p is not None and not p.IsReadOnly:
            p.Set(w_ft)
            w_set = True
            break
    d_set = False
    for pname in ["Depth", "Profundidad", "h", "d"]:
        p = new_symbol.LookupParameter(pname)
        if p is not None and not p.IsReadOnly:
            p.Set(d_ft)
            d_set = True
            break

    # Activate before first use
    if not new_symbol.IsActive:
        new_symbol.Activate()
    doc.Regenerate()

    return new_symbol


def _create_pedestal_directshape(doc, center_x, center_y, base_z,
                                 width_mm, depth_mm, height_mm):
    """Create a pedestal as a DirectShape in OST_StructuralColumns.

    Works from background thread (pyRevit Routes).
    All dimensions in mm, coordinates in feet (Revit internal).
    Must be called inside an open Transaction.
    Returns the DirectShape element.
    """
    w_ft = width_mm / 304.8
    d_ft = depth_mm / 304.8
    h_ft = height_mm / 304.8

    # Rectangular profile at base elevation
    p0 = XYZ(center_x - w_ft / 2, center_y - d_ft / 2, base_z)
    p1 = XYZ(center_x + w_ft / 2, center_y - d_ft / 2, base_z)
    p2 = XYZ(center_x + w_ft / 2, center_y + d_ft / 2, base_z)
    p3 = XYZ(center_x - w_ft / 2, center_y + d_ft / 2, base_z)

    perfil = CurveLoop()
    perfil.Append(Line.CreateBound(p0, p1))
    perfil.Append(Line.CreateBound(p1, p2))
    perfil.Append(Line.CreateBound(p2, p3))
    perfil.Append(Line.CreateBound(p3, p0))

    lista = List[CurveLoop]()
    lista.Add(perfil)

    solido = GeometryCreationUtilities.CreateExtrusionGeometry(
        lista, XYZ.BasisZ, h_ft)

    cat_id = ElementId(BuiltInCategory.OST_StructuralColumns)
    ds = DirectShape.CreateElement(doc, cat_id)
    ds.SetShape([solido])
    return ds


def _get_level_at_elevation_zero(doc):
    """Return the level closest to elevation 0.0 (Nivel 0 / planta baja)."""
    levels = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    if not levels:
        return None
    levels.sort(key=lambda lv: abs(lv.Elevation))
    return levels[0]


# ------------------------------------------------------------------
# Diagnostics endpoint
@api.route("/debug_footing_params/", methods=["GET"])
def debug_footing_params(doc, request):
    """List all FamilySymbol params in StructuralFoundation category."""
    out = []
    try:
        collector = FilteredElementCollector(doc).OfCategory(
            DB.BuiltInCategory.OST_StructuralFoundation).OfClass(FamilySymbol)
        for sym in collector:
            try:
                sname = DB.Element.Name.GetValue(sym)
            except Exception:
                sname = "?"
            try:
                fname = sym.Family.Name
            except Exception:
                fname = "?"
            out.append("Type: %s (Family: %s)" % (sname, fname))
            for p in sym.Parameters:
                try:
                    val = ""
                    st = str(p.StorageType)
                    if st == "Double":
                        val = "%.4f ft (%.1f mm)" % (p.AsDouble(), p.AsDouble() * 304.8)
                    elif st == "String":
                        val = str(p.AsString() or "")
                    elif st == "Integer":
                        val = str(p.AsInteger())
                    out.append("  %s = %s [ro=%s]" % (
                        p.Definition.Name, val, p.IsReadOnly))
                except Exception:
                    pass
            break  # only first type
    except Exception as e:
        out.append("ERROR: %s" % str(e))
    return routes.make_response(data={"params": out})


# ------------------------------------------------------------------

@api.route("/debug_column_family/", methods=["GET"])
def debug_column_family(doc, request):
    """Diagnose why the concrete column family fails to load."""
    import os, tempfile
    out = []
    app = doc.Application

    # 1. Template path
    try:
        tpl = app.FamilyTemplatePath
        out.append("FamilyTemplatePath: %s" % tpl)
    except Exception as e:
        out.append("FamilyTemplatePath ERROR: %s" % str(e))
        tpl = None

    # 2. Find template file
    template_file = None
    candidates = []
    if tpl:
        candidates = [
            os.path.join(tpl, "Metric Structural Column.rft"),
            os.path.join(tpl, "English", "Metric Structural Column.rft"),
        ]
    candidates += [
        r"C:\ProgramData\Autodesk\RVT 2024\Family Templates\English\Metric Structural Column.rft",
        r"C:\ProgramData\Autodesk\RVT 2024\Family Templates\Metric Structural Column.rft",
    ]
    for p in candidates:
        exists = os.path.exists(p)
        out.append("Template %s -> %s" % (p, "EXISTS" if exists else "NOT FOUND"))
        if exists and template_file is None:
            template_file = p

    if template_file is None:
        return routes.make_response(data={"steps": out, "result": "NO TEMPLATE FOUND"})

    # 3. NewFamilyDocument
    family_doc = None
    try:
        family_doc = app.NewFamilyDocument(template_file)
        out.append("NewFamilyDocument: OK, IsFamilyDocument=%s" % family_doc.IsFamilyDocument)
    except Exception as e:
        out.append("NewFamilyDocument ERROR: %s" % str(e))
        return routes.make_response(data={"steps": out, "result": "FAILED at NewFamilyDocument"})

    # 4. FamilyManager params
    try:
        fm = family_doc.FamilyManager
        params = [fp.Definition.Name for fp in fm.Parameters]
        out.append("FamilyManager params: %s" % str(params))
        out.append("CurrentType: %s" % str(fm.CurrentType))
    except Exception as e:
        out.append("FamilyManager ERROR: %s" % str(e))

    # 5. SaveAs
    temp_path = os.path.join(tempfile.gettempdir(), "PedestalConcreto_test.rfa")
    try:
        save_opts = SaveAsOptions()
        save_opts.OverwriteExistingFile = True
        family_doc.SaveAs(temp_path, save_opts)
        family_doc.Close(False)
        family_doc = None
        out.append("SaveAs: OK -> %s" % temp_path)
    except Exception as e:
        out.append("SaveAs ERROR: %s" % str(e))
        if family_doc:
            try: family_doc.Close(False)
            except Exception: pass
        return routes.make_response(data={"steps": out, "result": "FAILED at SaveAs"})

    # 6. LoadFamily via file path (old approach — known to return ok=False)
    try:
        family_ref = clr.Reference[Family]()
        ok = doc.LoadFamily(temp_path, _FamilyLoadOption(), family_ref)
        fam = family_ref.Value
        out.append("doc.LoadFamily(path) ok=%s family=%s" % (ok, fam.Name if fam else "None"))
    except Exception as e:
        out.append("doc.LoadFamily(path) ERROR: %s" % str(e))

    # 7. LoadFamily via family_doc (NEW approach — in-memory, no SaveAs needed)
    family_doc2 = None
    try:
        family_doc2 = app.NewFamilyDocument(template_file)
        fm2 = family_doc2.FamilyManager
        t2 = Transaction(family_doc2, "setup2")
        t2.Start()
        try:
            if fm2.CurrentType is None:
                fm2.NewType("Default")
            t2.Commit()
        except Exception:
            try: t2.RollBack()
            except Exception: pass
        fam2 = family_doc2.LoadFamily(doc, _FamilyLoadOption())
        family_doc2.Close(False)
        family_doc2 = None
        out.append("family_doc.LoadFamily(doc) -> %s" % (fam2.Name if fam2 else "None"))
    except Exception as e:
        out.append("family_doc.LoadFamily(doc) ERROR: %s" % str(e))
        if family_doc2:
            try: family_doc2.Close(False)
            except Exception: pass

    return routes.make_response(data={"steps": out, "result": "DONE"})


# ------------------------------------------------------------------
# Foundations: API endpoint
# ------------------------------------------------------------------

@api.route("/create_foundations/", methods=["POST"])
def create_foundations(doc, request):
    """Create isolated footings + pedestals at grid intersections.

    Supports two modes:
    1. Auto mode (no assignments): place at ALL intersections using auto-classification
    2. Manual mode (with assignments): place only at specified intersections

    Expected JSON:
    {
        "central": {"width": 1500, ..., "pedestal_width": 400, ...},
        "esquinera": {...},
        "lindero": {...},
        "level_name": "",
        "assignments": [  (optional - if present, use manual mode)
            {"grid_x": "A", "grid_y": "1", "name": "Z-01", "type": "central",
             "width": 1500, "length": 1500, "thickness": 400,
             "pedestal_width": 400, "pedestal_length": 400, "pedestal_height": 600},
            ...
        ]
    }
    """
    _ensure_dialog_handler()
    data = request.data

    default_cfg = {"width": 1500.0, "length": 1500.0, "thickness": 400.0,
                   "pedestal_width": 400.0, "pedestal_length": 400.0, "pedestal_height": 600.0}
    central_cfg = data.get("central", default_cfg)
    esquinera_cfg = data.get("esquinera", default_cfg)
    lindero_cfg = data.get("lindero", default_cfg)
    level_name = data.get("level_name", "")
    assignments = data.get("assignments", None)

    placed = {"central": 0, "esquinera": 0, "lindero": 0}
    pedestals_placed = [0]
    details = []
    dbg = []  # debug log devuelto en la respuesta

    try:
        app = doc.Application
        dbg.append("app OK")

        # Find or load families OUTSIDE any transaction
        # (LoadFamily requires no open transaction)
        family = [None]
        col_family = [None]

        try:
            family[0] = _find_footing_family(doc, app)
            dbg.append("footing_family: %s" % (family[0].Name if family[0] else "None"))
        except Exception as e:
            dbg.append("ERROR _find_footing_family: %s" % str(e))

        if family[0] is None:
            try:
                w = central_cfg.get("width", 1500.0) / 304.8
                l = central_cfg.get("length", 1500.0) / 304.8
                h = central_cfg.get("thickness", 400.0) / 304.8
                family[0] = _create_footing_family_from_template(doc, app, "Zapata", w, l, h)
                dbg.append("footing from template: %s" % (family[0].Name if family[0] else "None"))
            except Exception as e:
                dbg.append("ERROR _create_footing_family_from_template: %s" % str(e))

        try:
            # Pass first pedestal dimensions so extrusion matches
            ped_w = float(central_cfg.get("pedestal_width", 400.0))
            ped_d = float(central_cfg.get("pedestal_length", 400.0))
            col_family[0] = _find_column_family(doc, app, ped_w, ped_d)
            dbg.append("col_family: %s" % (col_family[0].Name if col_family[0] else "None"))
        except Exception as e:
            import traceback as tb
            err_txt = tb.format_exc()
            dbg.append("ERROR col_family: %s" % str(e))
            # Write full traceback to file for debugging
            try:
                err_path = os.path.join(os.path.expanduser("~"), "Desktop", "pedestal_error.txt")
                f = open(err_path, "w")
                f.write(err_txt)
                f.close()
                dbg.append("traceback saved to: %s" % err_path)
            except Exception:
                pass

        if family[0] is None:
            return routes.make_response(
                status=500,
                data={"success": False, "error": "No se pudo cargar ni crear la familia de zapatas",
                      "debug": dbg},
            )

        # Get all grid intersections (needed for both modes)
        intersections = _get_grid_intersections(doc)
        if not intersections:
            return routes.make_response(
                status=400,
                data={"success": False, "error": "No se encontraron intersecciones de grids. Cree grids primero."},
            )

        # Build intersection lookup by grid names
        int_by_grids = {}
        for info in intersections:
            key = (info["grid_v"], info["grid_h"])  # (vertical_name, horizontal_name)
            int_by_grids[key] = info

        # Get target level
        target_level = None
        if level_name:
            lvl_collector = FilteredElementCollector(doc).OfClass(Level)
            for lv in lvl_collector:
                if lv.Name == level_name:
                    target_level = lv
                    break
        if target_level is None:
            target_level = _get_lowest_level(doc)
        if target_level is None:
            return routes.make_response(
                status=400,
                data={"success": False, "error": "No hay niveles en el proyecto. Cree niveles primero."},
            )

        top_level = _get_next_level_above(doc, target_level)

        # Determine placement list
        if assignments is not None and len(assignments) > 0:
            # ── MANUAL MODE: only place at assigned intersections ──
            placement_list = []
            for asgn in assignments:
                gx_name = asgn.get("grid_x", "")
                gy_name = asgn.get("grid_y", "")
                # Try both orderings for the lookup
                info = int_by_grids.get((gx_name, gy_name))
                if info is None:
                    info = int_by_grids.get((gy_name, gx_name))
                if info is None:
                    # Try matching by name in any combination
                    for k, v in int_by_grids.items():
                        if set(k) == set([gx_name, gy_name]):
                            info = v
                            break
                if info is not None:
                    placement_list.append({
                        "point": info["point"],
                        "category": asgn.get("type", info.get("category", "central")),
                        "grid_h": info["grid_h"],
                        "grid_v": info["grid_v"],
                        "sign_x": info.get("sign_x", 0),
                        "sign_y": info.get("sign_y", 0),
                        "edge_type": info.get("edge_type", "none"),
                        "cfg_override": {
                            "width": float(asgn.get("width", 1500.0)),
                            "length": float(asgn.get("length", 1500.0)),
                            "thickness": float(asgn.get("thickness", 400.0)),
                            "pedestal_width": float(asgn.get("pedestal_width", 400.0)),
                            "pedestal_length": float(asgn.get("pedestal_length", 400.0)),
                            "pedestal_height": float(asgn.get("pedestal_height", 600.0)),
                        },
                    })
        else:
            # ── AUTO MODE: place at ALL intersections ──
            placement_list = []
            for info in intersections:
                placement_list.append({
                    "point": info["point"],
                    "category": info["category"],
                    "grid_h": info["grid_h"],
                    "grid_v": info["grid_v"],
                    "sign_x": info.get("sign_x", 0),
                    "sign_y": info.get("sign_y", 0),
                    "edge_type": info.get("edge_type", "none"),
                    "cfg_override": None,
                })

        if not placement_list:
            return routes.make_response(
                status=400,
                data={"success": False, "error": "No se encontraron intersecciones para colocar."},
            )

        # Nivel 0: level closest to elevation 0.0 (planta baja)
        nivel_0 = _get_level_at_elevation_zero(doc)
        nivel_0_z = nivel_0.Elevation if nivel_0 is not None else 0.0

        # ── PRE-CREATE all unique footing families BEFORE transaction ──
        # (LoadFamily requires no open transaction)
        footing_family_cache = {}  # "WxLxT" → FamilySymbol

        def _get_footing_sym_for_size(w_mm, l_mm, t_mm):
            fkey = "%dx%dx%d" % (int(w_mm), int(l_mm), int(t_mm))
            if fkey in footing_family_cache:
                return footing_family_cache[fkey]

            # Check if family already loaded
            fam_name = "Zapata_%s" % fkey
            foot_cat_id = int(DB.BuiltInCategory.OST_StructuralFoundation)
            for fam in FilteredElementCollector(doc).OfClass(Family):
                try:
                    fc = fam.FamilyCategory
                    if fc and fc.Id.IntegerValue == foot_cat_id and fam.Name == fam_name:
                        sid = list(fam.GetFamilySymbolIds())[0]
                        sym = doc.GetElement(sid)
                        footing_family_cache[fkey] = sym
                        return sym
                except Exception:
                    pass

            # Create new family with exact dimensions
            try:
                w_ft = w_mm / 304.8
                l_ft = l_mm / 304.8
                t_ft = t_mm / 304.8
                new_fam = _create_footing_family_from_template(
                    doc, app, fam_name, w_ft, l_ft, t_ft)
                if new_fam:
                    sid = list(new_fam.GetFamilySymbolIds())[0]
                    sym = doc.GetElement(sid)
                    footing_family_cache[fkey] = sym
                    return sym
            except Exception as e:
                dbg.append("footing_create_err %s: %s" % (fkey, str(e)))
            return None

        # Collect all unique footing sizes from placement list
        all_sizes = set()
        if assignments is not None and len(assignments) > 0:
            for asgn in assignments:
                w = float(asgn.get("width", 1500.0))
                l = float(asgn.get("length", 1500.0))
                t = float(asgn.get("thickness", 400.0))
                all_sizes.add((w, l, t))
        else:
            for cfg in [central_cfg, esquinera_cfg, lindero_cfg]:
                w = float(cfg.get("width", 1500.0))
                l = float(cfg.get("length", 1500.0))
                t = float(cfg.get("thickness", 400.0))
                all_sizes.add((w, l, t))

        # Also add ROTATED sizes (w,l swapped) for linderos on vertical edges
        rotated_sizes = set()
        for (w, l, t) in all_sizes:
            if w != l:
                rotated_sizes.add((l, w, t))  # swapped
        all_sizes = all_sizes | rotated_sizes

        # Pre-create all needed footing families
        for (w, l, t) in all_sizes:
            sym = _get_footing_sym_for_size(w, l, t)
            if sym:
                dbg.append("footing_%dx%dx%d OK" % (int(w), int(l), int(t)))

        # Activate all symbols inside a transaction
        t_act = Transaction(doc, "Activate footing symbols")
        t_act.Start()
        try:
            for sym in footing_family_cache.values():
                if not sym.IsActive:
                    sym.Activate()
            doc.Regenerate()
            t_act.Commit()
        except Exception:
            try:
                t_act.RollBack()
            except Exception:
                pass

        def do_create_and_place():
            configs = {
                "central": central_cfg,
                "esquinera": esquinera_cfg,
                "lindero": lindero_cfg,
            }

            doc.Regenerate()

            for item in placement_list:
                pt = item["point"]
                cat = item["category"]
                override = item.get("cfg_override")

                if override is not None:
                    w = float(override.get("width", 1500.0))
                    l = float(override.get("length", 1500.0))
                    t = float(override.get("thickness", 400.0))
                    thickness_mm = t
                else:
                    cfg_used = configs.get(cat, default_cfg)
                    w = float(cfg_used.get("width", 1500.0))
                    l = float(cfg_used.get("length", 1500.0))
                    t = float(cfg_used.get("thickness", 400.0))
                    thickness_mm = t

                # For lindero on vertical edge (A/D): ROTATE footing by swapping W and L
                edge = item.get("edge_type", "none")
                if cat == "lindero" and edge == "v" and w != l:
                    w, l = l, w  # swap width and length = 90° rotation

                # Get pre-created footing symbol for this exact size
                fkey = "%dx%dx%d" % (int(w), int(l), int(t))
                footing_sym = footing_family_cache.get(fkey)

                # If rotated size not pre-created, create it now
                if footing_sym is None and cat == "lindero" and edge == "v":
                    sym = _get_footing_sym_for_size(w, l, t)
                    if sym:
                        footing_family_cache[fkey] = sym
                        footing_sym = sym

                if footing_sym is None:
                    continue

                # Footing position:
                #   central:   centered on intersection
                #   esquinera: CORNER at intersection, body extends toward building center
                #   lindero:   EDGE at intersection, body extends toward building center
                # Pedestal stays at intersection (pt.X, pt.Y) for all types
                w_f = w / 304.8
                l_f = l / 304.8
                sx = item.get("sign_x", 0)
                sy = item.get("sign_y", 0)

                if cat == "esquinera":
                    # Pedestal center at intersection. Footing shifted so pedestal
                    # is fully inside, near the outer corner of the footing.
                    pw_ft = float(central_cfg.get("pedestal_width", 400.0)) / 304.8
                    pl_ft = float(central_cfg.get("pedestal_length", 400.0)) / 304.8
                    if override is not None:
                        pw_ft = float(override.get("pedestal_width", 400.0)) / 304.8
                        pl_ft = float(override.get("pedestal_length", 400.0)) / 304.8
                    foot_x = pt.X + sx * (w_f - pw_ft) / 2.0
                    foot_y = pt.Y + sy * (l_f - pl_ft) / 2.0
                elif cat == "lindero":
                    # Pedestal centered at intersection. Footing shifted so pedestal
                    # is fully inside, near the outer edge of the footing.
                    _pw_ft = float(central_cfg.get("pedestal_width", 400.0)) / 304.8
                    _pl_ft = float(central_cfg.get("pedestal_length", 400.0)) / 304.8
                    if override is not None:
                        _pw_ft = float(override.get("pedestal_width", 400.0)) / 304.8
                        _pl_ft = float(override.get("pedestal_length", 400.0)) / 304.8
                    edge = item.get("edge_type", "none")
                    if edge == "v":
                        # Left/right edge (axes A/D): shift footing in X toward center
                        foot_x = pt.X + sx * (w_f - _pw_ft) / 2.0
                        foot_y = pt.Y
                    elif edge == "h":
                        # Top/bottom edge (axes 1/3): shift footing in Y toward center
                        foot_x = pt.X
                        foot_y = pt.Y + sy * (l_f - _pl_ft) / 2.0
                    else:
                        foot_x = pt.X
                        foot_y = pt.Y
                else:
                    foot_x = pt.X
                    foot_y = pt.Y

                footing_pt = DB.XYZ(foot_x, foot_y, 0)
                doc.Create.NewFamilyInstance(
                    footing_pt, footing_sym, target_level, StructuralType.Footing)
                placed[cat] += 1

                # Place pedestal as structural column (supports rebar).
                # Family created with NewExtrusion geometry.
                # Routes dispatches to main thread → LoadFamily works.
                if col_family[0] is not None:
                    footing_thickness_ft = thickness_mm / 304.8

                    if override is not None:
                        pw = float(override.get("pedestal_width", 400.0))
                        pl = float(override.get("pedestal_length", 400.0))
                    else:
                        cfg_used = configs.get(cat, default_cfg)
                        pw = float(cfg_used.get("pedestal_width", 400.0))
                        pl = float(cfg_used.get("pedestal_length", 400.0))

                    ct_name = "Pedestal %dx%d" % (int(pw), int(pl))
                    col_sym = _get_or_create_column_type(
                        doc, col_family[0], ct_name, pw, pl)

                    if col_sym is not None:
                        # Get pedestal height from GUI config
                        if override is not None:
                            ped_h_mm = float(override.get("pedestal_height", 600.0))
                        else:
                            cfg_used = configs.get(cat, default_cfg)
                            ped_h_mm = float(cfg_used.get("pedestal_height", 600.0))

                        ped_h_ft = ped_h_mm / 304.8

                        # Pedestal: CENTER always at intersection for ALL types
                        ped_x = pt.X
                        ped_y = pt.Y

                        ped_pt = DB.XYZ(ped_x, ped_y, 0)
                        try:
                            col_inst = doc.Create.NewFamilyInstance(
                                ped_pt, col_sym, target_level, StructuralType.Column)

                            # Base offset = footing thickness (pedestal sits on top of footing)
                            base_off = col_inst.get_Parameter(
                                DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM)
                            if base_off and not base_off.IsReadOnly:
                                base_off.Set(footing_thickness_ft)

                            # Top: same level, offset = footing_thickness + pedestal_height
                            top_offset_ft = footing_thickness_ft + ped_h_ft

                            top_lv = col_inst.get_Parameter(
                                DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
                            if top_lv and not top_lv.IsReadOnly:
                                top_lv.Set(target_level.Id)

                            top_off = col_inst.get_Parameter(
                                DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
                            if top_off and not top_off.IsReadOnly:
                                top_off.Set(top_offset_ft)

                            pedestals_placed[0] += 1

                            if pedestals_placed[0] == 1:
                                doc.Regenerate()
                                # Read back actual constraint values
                                rb_base = col_inst.get_Parameter(
                                    DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM)
                                rb_top_lv = col_inst.get_Parameter(
                                    DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
                                rb_top_off = col_inst.get_Parameter(
                                    DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
                                dbg.append("ped: base_off_set=%.3f" % footing_thickness_ft)
                                dbg.append("top_off_set=%.3f" % top_offset_ft)
                                dbg.append("base_off_read=%.3f" % (rb_base.AsDouble() if rb_base else -1))
                                dbg.append("top_lv_read=%s" % (str(rb_top_lv.AsElementId().IntegerValue) if rb_top_lv else "N/A"))
                                dbg.append("top_off_read=%.3f" % (rb_top_off.AsDouble() if rb_top_off else -1))
                                dbg.append("target_lv_id=%d elev=%.3f" % (target_level.Id.IntegerValue, target_level.Elevation))
                                dbg.append("nivel0_z=%.3f" % nivel_0_z)
                                bb = col_inst.get_BoundingBox(None)
                                if bb:
                                    ht_ft = bb.Max.Z - bb.Min.Z
                                    dbg.append("BB z=%.2f..%.2f h=%.2fft=%.0fmm" % (
                                        bb.Min.Z, bb.Max.Z, ht_ft, ht_ft * 304.8))
                                else:
                                    dbg.append("BB=None")
                        except Exception as pe:
                            dbg.append("PEDESTAL_ERR: %s" % str(pe))

                details.append({
                    "grid_h": item["grid_h"],
                    "grid_v": item["grid_v"],
                    "category": cat,
                })

        _run_transaction(doc, "Create foundations and pedestals", do_create_and_place)

        total = placed["central"] + placed["esquinera"] + placed["lindero"]
        dbg.append("placed=%d pedestals=%d" % (total, pedestals_placed[0]))
        return routes.make_response(
            data={
                "success": True,
                "total": total,
                "central": placed["central"],
                "esquinera": placed["esquinera"],
                "lindero": placed["lindero"],
                "pedestals": pedestals_placed[0],
                "details": details,
                "mode": "manual" if assignments else "auto",
                "debug": dbg,
            },
        )

    except Exception as exc:
        import traceback
        return routes.make_response(
            status=500,
            data={"success": False, "error": str(exc),
                  "traceback": traceback.format_exc(),
                  "debug": dbg},
        )
