"""Тести Board Studio у Python IngeTrazo, без вікна. Запуск: ./scripts/test.sh"""
from __future__ import annotations

import importlib
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.environ.get("INGETRAZO_ROOT", "/app/ingetrazo"))

from PySide6.QtCore import QCoreApplication, QPointF, Qt   # noqa: E402
from PySide6.QtGui import QVector3D as V                   # noqa: E402
from PySide6.QtWidgets import QApplication, QToolBar       # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


def close(a, b, tol=1e-6):
    return (a - b).length() < tol


def coords(group, axis):
    return {round(getattr(v.position, axis)(), 6) for f in group.mesh.faces for v in f.loop}


def load_plugin():
    from core.extensions import discover_plugins
    plugins, errors = discover_plugins([PROJECT])
    check(not errors, f"load errors: {errors}")
    plug = [p for p in plugins if p.stem == "board_studio"]
    check(len(plug) == 1 and plug[0].tools == [] and callable(plug[0].setup),
          "board_studio: setup only, no one-shot tools")
    return plug[0], importlib.import_module("ingetrazo_plugin_board_studio.tool")


def test_geometry(t):
    p1, p2, p3 = V(0, 0, 0), V(1, 0, 0), V(0.3, 0, 0.5)
    final, raw, n = t.panel_points(p1, p2, p3)
    check(close(final[2], V(1, 0, 0.5)) and close(final[3], V(0, 0, 0.5)), f"corners {final}")
    check(close(n, V(0, -1, 0)), f"normal {n}")
    final, raw, _ = t.panel_points(p1, p2, p3, 0.1, 0.05)
    check(close(final[0], V(0.1, 0, 0.05)) and close(final[2], V(0.9, 0, 0.45)), f"offsets {final}")
    check(close(raw[2], V(1, 0, 0.5)), "raw corners kept")
    check(close(t.panel_points(p1, p2, p3, 0.6)[0][0], p1), "too-large offset ignored")
    check(t.panel_points(p1, p1, p3) is None, "degenerate base")
    check(t.panel_points(p1, p2, V(2, 0, 0)) is None, "zero height")
    loops = t.box_loops(final, n * 0.016)
    centre = sum((p for lp in loops for p in lp), V()) / 24
    check(all(V.dotProduct(t.loop_normal(lp), sum(lp, V()) / 4 - centre) > 0 for lp in loops),
          "faces point outwards")
    check(len(t.box_edges(final, n)) == 12, "12 box edges")
    check(close(t.default_height_dir(V(1, 0, 0)), V(0, 0, 1)), "default up")
    check(close(t.default_height_dir(V(0, 0, 1)), V(0, 1, 0)), "vertical base → Y")


class FakeViewport:
    def __init__(self, scene, history):
        self.scene, self.history = scene, history
        self.axis_lock = None
        self.camera = SimpleNamespace(target=V(0, 0, 0), eye=lambda: V(5, -5, 5))

    def flash_status(self, text, msec=2500):
        pass

    def update(self):
        pass

    def _pixel_to_ray(self, x, y):
        return None, None


def ctx(vp, p, kind="endpoint"):
    from tools.base import ToolContext
    return ToolContext(vp, V(p), QPointF(0, 0), Qt.NoModifier, SimpleNamespace(kind=kind))


def test_tool(t):
    from core.history import History
    from core.scene import Scene
    scene = Scene()
    hist = History(scene)
    vp = FakeViewport(scene, hist)
    tool = t.ThreePointPanelTool(0.018)
    tool.on_activate(vp)

    # 3 кліки: 600 мм уздовж X, 720 мм угору (перша точка — в початку координат)
    tool.on_click(ctx(vp, V(0, 0, 0)))
    check(tool.start_point is not None, "start_point at the origin")
    tool.on_hover(ctx(vp, V(0.6, 0, 0)))
    check(len(tool.rubber_band_lines()) == 1, "segment preview")
    tool.on_click(ctx(vp, V(0.6, 0, 0)))
    check(tool.vcb_label == "Height", "VCB label")
    tool.on_hover(ctx(vp, V(0.2, 0, 0.72)))
    check(len(tool.preview_faces()) == 6, "box preview faces")
    check(len(tool.rubber_band_lines()) == 1 + 12, "preview lines")
    check(tool.guide_preview_lines() == [], "no raw outline without offsets")
    tool.on_click(ctx(vp, V(0.2, 0, 0.72)))
    check(len(scene.groups) == 1, f"one group; {hist.last_error}")
    g = scene.groups[0]
    check(len(g.mesh.faces) == 6 and len(g.mesh.edges) == 12, "6 faces, 12 edges")
    from core.solids import is_solid
    check(is_solid(g), "closed solid")
    check(g.ext["board_studio"] == {"length": 0.6, "width": 0.72, "thickness": 0.018,
                                   "offset_length": 0.0, "offset_width": 0.0}, f"ext {g.ext}")
    check(g.name == "Panel 1", g.name)
    check(tool.start_point is None, "reset after creation")
    check(coords(g, "y") == {0.0, -0.018}, f"push toward -Y: {coords(g, 'y')}")

    # Ctrl + введення з клавіатури
    tool.on_key(vp, Qt.Key_Control, Qt.ControlModifier)
    check(tool.flip, "Ctrl flips")
    tool.on_click(ctx(vp, V(0, 1, 0)))
    tool.on_hover(ctx(vp, V(1, 1, 0)))
    check(tool.on_value(vp, 0.5) and close(tool.points[1], V(0.5, 1, 0)), "typed length")
    tool.on_hover(ctx(vp, V(0.5, 1, 0.3)))
    check(tool.on_value(vp, 0.4), "typed height")
    g2 = scene.groups[-1]
    check(coords(g2, "y") == {1.0, 1.018}, f"flipped push toward +Y: {coords(g2, 'y')}")
    check(coords(g2, "z") == {0.0, 0.4}, "typed height")
    check(g2.name == "Panel 2", g2.name)

    # Нульова висота — відмова; Esc; undo
    for p in (V(0, 0, 0), V(1, 0, 0), V(2, 0, 0)):
        tool.on_click(ctx(vp, p))
    check(len(scene.groups) == 2 and len(tool.points) == 2, "zero height refused")
    tool.on_cancel(vp)
    check(not tool.points, "Esc resets")
    hist.undo()
    check(len(scene.groups) == 1, "undo removes panel")

    # Відступи + прилипання висоти до Z (~1.1° від осі)
    tool.thickness, tool.offset_length, tool.offset_width = 0.016, 0.01, 0.02
    tool.on_click(ctx(vp, V(0, 0, 0)))
    tool.on_click(ctx(vp, V(1, 0, 0)))
    tool.on_hover(ctx(vp, V(1, 0.02, 1.0), kind="none"))
    check(len(tool.guide_preview_lines()) == 4, "raw outline with offsets")
    tool.on_click(ctx(vp, V(1, 0.02, 1.0), kind="none"))
    g3 = scene.groups[-1]
    check(coords(g3, "x") == {0.01, 0.99}, f"length offsets {coords(g3, 'x')}")
    check(coords(g3, "z") == {0.02, round(math.hypot(0.02, 1.0) - 0.02, 6)},
          f"height snapped to Z {coords(g3, 'z')}")

    # Блокування осі стрілкою: висота строго вздовж Y
    vp.axis_lock = "y"
    tool.on_click(ctx(vp, V(0, 0, 0)))
    tool.on_click(ctx(vp, V(1, 0, 0)))
    tool.on_click(ctx(vp, V(0.5, 0.3, 0.8), kind="none"))
    check(coords(scene.groups[-1], "z") == {0.0, -0.016} or
          coords(scene.groups[-1], "z") == {0.0, 0.016}, "axis lock keeps it flat")


def test_setup(plug, t):
    QCoreApplication.setOrganizationName("board-studio-tests")
    QCoreApplication.setApplicationName("board-studio-tests")
    app = QApplication.instance() or QApplication([])
    from views.extension_api import ExtensionApp
    from views.main_window import MainWindow
    win = MainWindow()
    plug.setup(ExtensionApp(win, plug.stem))
    sub = [a.menu() for a in win._ext_menu.actions() if a.menu() and a.text() == "Board Studio"]
    check(sub and [a.text() for a in sub[0].actions()]
          == ["New 3-Point Panel", "Next 3-Point Panel"], "menu entries")
    bar = win.findChild(QToolBar, "extension_board_studio_toolbar")
    check(bar is not None and all(not a.icon().isNull() for a in bar.actions()), "toolbar with icons")
    bar.actions()[1].trigger()                      # Next: без діалогу
    tool = win.viewport.active_tool
    check(isinstance(tool, t.ThreePointPanelTool), "tool active")
    check("Click first corner" in win.status_hint, f"hint: {win.status_hint}")
    del app


def main():
    plug, t = load_plugin()
    test_geometry(t)
    test_tool(t)
    test_setup(plug, t)
    if FAILS:
        sys.exit(f"\n{len(FAILS)} failure(s)")
    print("OK")


if __name__ == "__main__":
    main()
