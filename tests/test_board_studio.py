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

    #: грань, яку «бачить» курсор (тести режиму крайки)
    picked = None

    def pick_face_any(self, x, y):
        return self.picked, None


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
    check(all(f.attrs and f.attrs.get("texture") for f in tool.preview_faces()), "textured preview")
    check(len(tool.rubber_band_lines()) == 1 + 12, "preview lines")
    check(tool.guide_preview_lines() == [], "no raw outline without offsets")
    tool.on_click(ctx(vp, V(0.2, 0, 0.72)))
    check(len(scene.groups) == 1, f"one group; {hist.last_error}")
    g = scene.groups[0]
    check(len(g.mesh.faces) == 6 and len(g.mesh.edges) == 12, "6 faces, 12 edges")
    from core.solids import is_solid
    check(is_solid(g), "closed solid")
    check_paint(scene, g, along_length=V(1, 0, 0), edge="chipboard")
    check(g.ext["board_studio"] == {"material": "ДСП 16", "length": 0.6, "width": 0.72, "thickness": 0.018,
                                   "offset_length": 0.0, "offset_width": 0.0, "grain": "length",
                                   "article": "", "decor": "", "edges": [0.0] * 4, "holes": []},
          f"ext {g.ext}")
    check(g.axes is not None, "panel keeps its local axes")
    check(g.name == "Panel 1", g.name)
    check(tool.start_point is None, "reset after creation")
    check(coords(g, "y") == {0.0, -0.018}, f"push toward -Y: {coords(g, 'y')}")

    # Ctrl + введення з клавіатури
    tool.on_key(vp, Qt.Key_Control, Qt.ControlModifier)
    check(tool.flip, "Ctrl flips")
    tool.material = "МДФ 18"
    tool.on_click(ctx(vp, V(0, 1, 0)))
    tool.on_hover(ctx(vp, V(1, 1, 0)))
    check(tool.on_value(vp, 0.5) and close(tool.points[1], V(0.5, 1, 0)), "typed length")
    tool.on_hover(ctx(vp, V(0.5, 1, 0.3)))
    check(tool.on_value(vp, 0.4), "typed height")
    g2 = scene.groups[-1]
    check_paint(scene, g2, along_length=V(1, 0, 0), edge="fibreboard")
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


def check_paint(scene, g, along_length, edge):
    """Пласті — дуб з волокнами вздовж довжини, торці — текстура серцевини."""
    m = importlib.import_module("ingetrazo_plugin_board_studio.materials")
    oak, edge_name = m.SURFACES["oak"][0], m.SURFACES[edge][0]
    check(oak in scene.materials and edge_name in scene.materials, "materials registered")
    check(all(Path(mat.texture["path"]).is_file() for mat in scene.materials.values()),
          "texture files exist")
    big = [f for f in g.mesh.faces if f.attrs.get("mat") == oak]
    sides = [f for f in g.mesh.faces if f.attrs.get("mat") == edge_name]
    check(len(big) == 2 and len(sides) == 4, f"2 oak + 4 {edge} faces")
    for f in big:
        u = V(*f.attrs["texture"]["uvw"][:3])
        check(close(u.normalized(), along_length, 1e-5), f"grain along length: {u}")


def test_dialog(t):
    """Діалог: плита підставляє товщину, товщину можна виправити вручну."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QComboBox, QDialogButtonBox
    init = sys.modules["ingetrazo_plugin_board_studio"]
    tool = t.ThreePointPanelTool()

    def fill():
        dlg = QApplication.activeModalWidget()
        dlg.findChild(QComboBox).setCurrentText("ДСП 22")
        spins = dlg.findChildren(init.QDoubleSpinBox)
        check(math.isclose(spins[0].value(), 22.0), "preset sets thickness")
        spins[0].setValue(21.5)
        dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()

    QTimer.singleShot(0, fill)
    check(init._ask(None, tool), "dialog accepted")
    check(tool.material == "ДСП 22" and math.isclose(tool.thickness, 0.0215),
          f"dialog result {tool.material} {tool.thickness}")
    fresh = t.ThreePointPanelTool()
    init._load(fresh)
    check(fresh.material == "ДСП 22" and math.isclose(fresh.thickness, 0.0215), "settings persisted")


def test_setup(plug, t):
    QCoreApplication.setOrganizationName("board-studio-tests")
    QCoreApplication.setApplicationName("board-studio-tests")
    app = QApplication.instance() or QApplication([])
    from views.extension_api import ExtensionApp
    from views.main_window import MainWindow
    win = MainWindow()
    plug.setup(ExtensionApp(win, plug.stem))
    sub = [a.menu() for a in win._ext_menu.actions() if a.menu() and a.text() == "Board Studio"]
    texts = [a.text() for a in sub[0].actions() if not a.isSeparator()] if sub else []
    check(texts == ["New 3-Point Panel", "Next 3-Point Panel", "Panel Properties…", "Кріплення",
                    "Крайка", "Export DXF for ViyarPro…", "Show Holes", "Налаштування…"],
          f"menu entries {texts}")
    edge = [a for a in sub[0].actions() if a.text() == "Крайка"]
    edge[0].trigger()                               # панель крайок + режим крайки
    E = sys.modules["ingetrazo_plugin_board_studio.edgeband"]
    check(isinstance(win.viewport.active_tool, E.EdgeBandTool), "edge band mode active")
    dock = win.extension_panels().get("extension_board_studio_edges")
    check(dock is not None and win.viewport.active_tool.band is not None,
          "edges panel docked and a band chosen")
    fix = [a for a in sub[0].actions() if a.text() == "Кріплення"]
    fix[0].trigger()                                # відкриває бічну панель, без діалогу
    dock = win.extension_panels().get("extension_board_studio_fasteners")
    check(dock is not None, f"fasteners panel docked: {list(win.extension_panels())}")
    if dock is not None:
        ui = sys.modules["ingetrazo_plugin_board_studio.ui"]
        panel = dock.widget().findChild(ui.FastenersPanel) or dock.widget()
        check(isinstance(panel, ui.FastenersPanel) and panel.list.count() == 3,
              "panel lists the variants")
        check(not panel.add.isEnabled() and "Виділіть" in panel.head.text(),
              "nothing selected → install disabled")
    bar = win.findChild(QToolBar, "extension_board_studio_toolbar")
    check(bar is not None and all(not a.icon().isNull() for a in bar.actions() if not a.isSeparator()),
          "toolbar with icons")
    bar.actions()[1].trigger()                      # Next: без діалогу
    tool = win.viewport.active_tool
    check(isinstance(tool, t.ThreePointPanelTool), "tool active")
    check("Click first corner" in win.status_hint, f"hint: {win.status_hint}")
    del app


def make_panel(t, vp, p1, p2, p3, thickness=0.016, flip=False):
    tool = t.ThreePointPanelTool(thickness)
    tool.flip = flip
    tool.on_activate(vp)
    for p in (p1, p2, p3):
        tool.on_click(ctx(vp, p))
    return vp.scene.groups[-1]


def test_panels(t):
    """Локальні осі, властивості (кромка/текстура) з undo, шканти, експорт."""
    from core.group import carry_axes, transformed_mesh
    from core.history import History
    from core.scene import Scene
    from PySide6.QtGui import QMatrix4x4
    P = importlib.import_module("ingetrazo_plugin_board_studio.panels")
    ui = importlib.import_module("ingetrazo_plugin_board_studio.ui")
    m = importlib.import_module("ingetrazo_plugin_board_studio.materials")
    importlib.import_module("ingetrazo_plugin_board_studio.library").save(None)
    scene = Scene()
    hist = History(scene)
    vp = FakeViewport(scene, hist)

    # Дно 600×400×16 (верх на z=0.016) і бокова 400×720×16, що стоїть торцем на дні.
    bottom = make_panel(t, vp, V(0, 0, 0), V(0.6, 0, 0), V(0.6, 0.4, 0))
    side = make_panel(t, vp, V(0.016, 0, 0.016), V(0.016, 0.4, 0.016), V(0.016, 0.4, 0.736))
    pb, ps = P.Panel(bottom), P.Panel(side)
    check(all(abs(a - b) < 1e-3 for a, b in zip(pb.mm, (600, 400, 16))), f"bottom size {pb.mm}")
    check(all(abs(a - b) < 1e-3 for a, b in zip(ps.mm, (400, 720, 16))), f"side size {ps.mm}")
    check(sorted(str(pb.classify(f)) for f in bottom.mesh.faces)
          == ["0", "1", "2", "3", "bottom", "top"], "faces classified")

    # Поворот на 90° навколо Z: осі їдуть разом із сіткою, розміри ті самі.
    rot = QMatrix4x4()
    rot.rotate(90, 0, 0, 1)
    probe = make_panel(t, vp, V(2, 0, 0), V(2.5, 0, 0), V(2.5, 0.3, 0))
    probe.mesh = transformed_mesh(probe.mesh, rot)
    carry_axes(probe, rot)
    pp = P.Panel(probe)
    check(all(abs(a - b) < 1e-3 for a, b in zip(pp.mm, (500, 300, 16))), f"rotated size {pp.mm}")
    check(close(V(*pp.R[:, 0]), V(0, 1, 0), 1e-5), f"length axis turned {pp.R[:, 0]}")

    # Стара панель без осей: осі з геометрії.
    legacy = make_panel(t, vp, V(0, 2, 0), V(0.8, 2, 0), V(0.8, 2.3, 0))
    legacy.axes = None
    pl = P.Panel(legacy)
    check(all(abs(a - b) < 1e-3 for a, b in zip(pl.mm, (800, 300, 16))), f"legacy size {pl.mm}")

    # Властивості: кромка на стороні 0, текстура вздовж ширини, декор.
    scene.selection.clear()
    scene.selection.add(bottom)
    panels = P.selected_panels(scene)
    check(len(panels) == 1 and panels[0].group is bottom, "selected panels")
    data = panels[0].data
    data.update(edges=[0.8, 0, 0, 0], grain="width", article="151932", decor="KRONOSPAN 5307 SN")
    check(P.update_panels(vp, [(panels[0], data)]) is None, "properties applied")
    d = P.panel_data(bottom)
    check(d["edges"] == [0.8, 0, 0, 0] and d["grain"] == "width" and d["article"] == "151932",
          f"stored {d}")
    oak = m.SURFACES["oak"][0]
    pb = P.Panel(bottom)
    for f in bottom.mesh.faces:
        key = pb.classify(f)
        if key in ("top", "bottom"):
            u = V(*f.attrs["texture"]["uvw"][:3]).normalized()
            check(close(u, V(0, 1, 0), 1e-5) or close(u, V(0, -1, 0), 1e-5), f"grain along width {u}")
        elif key == 0:
            check(f.attrs["mat"] == oak, "banded edge wears the decor")
        else:
            check(f.attrs["mat"] == m.SURFACES["chipboard"][0], f"plain edge {key} shows the core")
    hist.undo()
    check(P.panel_data(bottom)["edges"] == [0.0] * 4, "undo properties")
    check(all(f.attrs["mat"] != oak or pb.classify(f) in ("top", "bottom")
              for f in bottom.mesh.faces), "undo paint")
    hist.redo()
    data = P.panel_data(bottom)
    data["grain"] = "none"
    P.update_panels(vp, [(P.Panel(bottom), data)])
    check(all(f.attrs["mat"] == m.PLAIN[0] for f in bottom.mesh.faces
              if pb.classify(f) in ("top", "bottom", 0)), "no texture → plain decor")

    # Стик: торець бокової (сторона 0, y=0 у її осях) лежить на верху дна.
    J = importlib.import_module("ingetrazo_plugin_board_studio.joints")
    FX = importlib.import_module("ingetrazo_plugin_board_studio.fasteners")
    js = J.joints(P.Panel(side), P.Panel(bottom))
    check(len(js) == 1 and js[0][1] is True and abs((js[0][3] - js[0][2]) - 0.4) < 1e-6,
          f"one joint along 400 mm on the top face: {js}")
    check(J.joints(P.Panel(bottom), P.Panel(side)) == [], "no joint the other way")
    check(FX.positions(400, 32, 256, 8) == [32.0, 200.0, 368.0], "3 dowels on 400 mm")
    check(len(FX.positions(300, 32, 256, 8)) == 2, "2 dowels on 300 mm")
    check(FX.positions(50, 32, 256, 8) == [25.0], "1 dowel on a short joint")
    scene.selection.clear()
    scene.selection.update([bottom, side])
    app = SimpleNamespace(viewport=vp, window=None)

    # Шкант: без жодного діалогу, усе — з варіанта.
    ui.place_fastener(app, "dowel_8x30")
    hs, hb = P.panel_data(side)["holes"], P.panel_data(bottom)["holes"]
    check(len(hs) == 3 and all(h["type"] == "side" and h["d"] == 8 and h["depth"] == 25
                               for h in hs), f"side holes {hs}")
    check(len(hb) == 3 and all(h["type"] == "face" and h["top"] and h["article"] == "38878"
                               for h in hb), f"face holes {hb}")
    check(sorted(round(h["y"]) for h in hb) == [32, 200, 368] and all(abs(h["x"] - 24) < 0.01 for h in hb),
          f"face holes under the side's mid-thickness: {hb}")
    check(all(abs(h["z"] - 8) < 0.01 for h in hs), "side holes at mid-thickness")
    for p in (P.Panel(side), P.Panel(bottom)):
        for h in P.panel_data(p.group)["holes"]:
            w, _n = J.hole_world(p, h)
            check(abs(w[2] - 0.016) < 1e-6, f"hole on the joint plane: {w}")
    ui.place_fastener(app, "dowel_8x30")                # повторно — зайняті місця не дублюються
    check(len(P.panel_data(side)["holes"]) == 3, "installed places are not doubled")
    ui.place_fastener(app, "confirmat_7x50")            # 37 мм біля шканта на 32 — зайнято
    check(len(P.panel_data(side)["holes"]) == 3, "a place next to a fastener is occupied")
    ui.remove_fasteners(app)

    # Конфірмат: наскрізний D7 знизу дна (зовнішній бік), Dside4.5 × 34.
    ui.place_fastener(app, "confirmat_7x50")
    hs, hb = P.panel_data(side)["holes"], P.panel_data(bottom)["holes"]
    check(len(hs) == 3 and all(h["d"] == 4.5 and h["depth"] == 34 for h in hs), f"confirmat edge {hs}")
    check(len(hb) == 3 and all(h["d"] == 7 and h["depth"] is None and not h["top"]
                               and h["group"] == "_ABF_screwInside" for h in hb), f"confirmat face {hb}")
    check(sorted(round(h["y"]) for h in hb) == [37, 200, 363], f"confirmat at 37 mm from the ends {hb}")

    # Мініфікс + шкант: чашка в пласті бокової з боку дна, 34 мм від торця.
    ui.remove_fasteners(app)
    ui.place_fastener(app, "minifix_15")
    hs, hb = P.panel_data(side)["holes"], P.panel_data(bottom)["holes"]
    cups = [h for h in hs if h["type"] == "face"]
    check(len(cups) == 2 and all(h["d"] == 15 and h["depth"] == 13 and h["top"]
                                 and abs(h["y"] - 34) < 0.01 for h in cups), f"minifix cups {cups}")
    edge = sorted((round(h["x"]), h["depth"]) for h in hs if h["type"] == "side")
    check(edge == [(37, 33), (69, 25), (331, 25), (363, 33)], f"minifix edge holes {edge}")
    stems = [h for h in hb if h["d"] == 5]
    check(len(stems) == 2 and all(h.get("layer") == "D8-DEPTH12-$38878" for h in stems),
          f"minifix stems on the dowel layer {stems}")
    check(sum(1 for h in hb if h["d"] == 8) == 2, "dowels next to minifix")

    scene.selection.clear()
    scene.selection.add(side)
    ui.remove_fasteners(app)
    check(P.panel_data(side)["holes"] == [] and P.panel_data(bottom)["holes"] == [],
          "remove fasteners clears both panels")
    hist.undo()
    check(len(P.panel_data(bottom)["holes"]) == 4, "undo remove")
    scene.selection.update([bottom, side])
    ui.remove_fasteners(app)

    # Рекомендації: місця на відступі від країв і посередині; користувач
    # відмічає потрібні, відступ і крок змінює в панелі.
    L = importlib.import_module("ingetrazo_plugin_board_studio.library")
    conf = L.find(L.fasteners(), "confirmat_7x50")
    cands, skipped = FX.candidates([P.Panel(side), P.Panel(bottom)], conf)
    check(not skipped and [(round(c.u), c.kind) for c in cands]
          == [(37, "end"), (200, "middle"), (363, "end")], f"suggested places {[c.u for c in cands]}")
    cands, _ = FX.candidates([P.Panel(side), P.Panel(bottom)], conf, offset=50, step=1000)
    check([round(c.u) for c in cands] == [50, 350], "offset and step from the panel")
    fp = ui.FastenersPanel(app)
    fp.list.setCurrentRow(1)                            # конфірмат
    check(fp.offset.value() == 37 and fp.step.value() == 256, "spins show the fastener's rules")
    check(fp.places.count() == 3 and not fp.add.isEnabled(), "three places, nothing marked")
    fp.offset.setValue(60)
    check(sorted(round(c.u) for c in fp.candidates) == [60, 200, 340], "offset changed in the panel")
    fp.toggle(fp.candidates[0].key)
    fp.places.item(2).setCheckState(Qt.Checked)
    check(len(fp.checked) == 2 and fp.add.text() == "Додати (2)", "two places marked")
    fp.add_checked()
    hb = P.panel_data(bottom)["holes"]
    check(sorted(round(h["y"]) for h in hb) == [60, 340], f"only marked places added {hb}")
    check([c.installed for c in fp.candidates] == [True, False, True] and not fp.checked,
          "added places shown as installed")
    fp.set_checked({c.key for c in fp.candidates if not c.installed})
    fp.add_checked()
    check(len(P.panel_data(bottom)["holes"]) == 3, "the middle one added later")
    hist.undo()
    check(len(P.panel_data(bottom)["holes"]) == 2, "each Add is one undo step")

    # Режим кріплення: клік біля місця відмічає його, клік по панелі — виділення.
    import numpy as np
    FT = importlib.import_module("ingetrazo_plugin_board_studio.fastenmode")
    fp.show()
    vp.world_to_pixels = lambda pts: (np.asarray(pts)[:, 0] * 1000, np.asarray(pts)[:, 1] * 1000,
                                      np.ones(len(pts), dtype=bool))
    tool = FT.FastenerTool(lambda: fp)
    fp.refresh()                                    # у вікні — on_document_changed
    free = next(c for c in fp.candidates if not c.installed)
    px = QPointF(free.point[0] * 1000 + 3, free.point[1] * 1000 - 2)
    from tools.base import ToolContext
    tool.on_click(ToolContext(vp, V(0, 0, 0), px, Qt.NoModifier, None))
    check(fp.checked == {free.key}, "click near a suggested place marks it")
    tool.on_click(ToolContext(vp, V(0, 0, 0), px, Qt.NoModifier, None))
    check(not fp.checked, "second click unmarks it")
    vp.picked = bottom.mesh.faces[0]
    far = QPointF(5000, 5000)
    tool.on_click(ToolContext(vp, V(0, 0, 0), far, Qt.NoModifier, None))
    check(bottom not in scene.selection, "click on a panel deselects it")
    tool.on_click(ToolContext(vp, V(0, 0, 0), far, Qt.NoModifier, None))
    check(bottom in scene.selection, "and selects it again")
    vp.picked = None
    fp.hide()
    ui.remove_fasteners(app)
    ui.place_fastener(app, "dowel_8x30")

    # Експорт: виділені панелі → DXF.
    import tempfile
    sys.path.insert(0, str(PROJECT / "tests"))
    import dxf_flatten
    scene.selection.clear()
    scene.selection.update([bottom, side])
    with tempfile.TemporaryDirectory() as tmp:
        path = ui.export_dxf(app, str(Path(tmp) / "out.dxf"))
        check(path is not None, "exported")
        ents, _b, _s = dxf_flatten.load(path)
    mats = {e.block for e in ents if e.kind == "INSERT" and e.label == "ABF_Flatten"}
    check("$151932____KRONOSPAN_5307_SN__THICKNESS_16" in mats and "THICKNESS_16" in mats,
          f"material blocks {mats}")
    tops = [e for e in ents if e.kind == "POLYFACE" and e.color == 7]
    check(len(tops) == 2, f"two panels exported, {len(tops)}")
    faces = [e for e in ents if e.kind == "CIRCLE" and e.layer == "D8-DEPTH12-$38878"]
    sides = [e for e in ents if e.kind == "CIRCLE" and e.layer == "Dside8"]
    check(len(faces) == 3 and len(sides) == 3, f"holes in DXF: {len(faces)} face, {len(sides)} side")
    check(all(abs(e.center[2] - 16) < 1e-6 for e in faces), "face holes on the top")
    cut = [e for e in ents if e.kind == "POLYLINE" and e.layer == "ABF_cuttingLines"]
    spans = sorted(round(max(p[k] for p in e.points) - min(p[k] for p in e.points), 2)
                   for e in cut for k in (0, 1))
    check(399.2 in spans or 599.2 in spans, f"cutting contour inset by the band: {spans}")


def test_properties_dialog(t):
    """Дві панелі з різним напрямком текстури: «(keep)» лишає своє, змінене
    поле — для всіх. Крайки в діалозі вже немає (вона — в режимі «Крайка»)."""
    from core.history import History
    from core.scene import Scene
    P = importlib.import_module("ingetrazo_plugin_board_studio.panels")
    ui = importlib.import_module("ingetrazo_plugin_board_studio.ui")
    scene = Scene()
    vp = FakeViewport(scene, History(scene))
    a = make_panel(t, vp, V(0, 0, 0), V(0.5, 0, 0), V(0.5, 0.3, 0))
    b = make_panel(t, vp, V(1, 0, 0), V(1.5, 0, 0), V(1.5, 0.3, 0))
    da = P.panel_data(a)
    da["grain"] = "none"
    P.update_panels(vp, [(P.Panel(a), da)])
    dlg = ui.PropertiesDialog(None, [P.Panel(a), P.Panel(b)])
    check(dlg.grain.currentData() == ui.KEEP, "mixed grain shows keep")
    check(not hasattr(dlg, "edges"), "no edge banding in the properties dialog")
    dlg.article.setText("$12345")
    new_a, new_b = dlg.apply_to(P.panel_data(a)), dlg.apply_to(P.panel_data(b))
    check(new_a["grain"] == "none" and new_b["grain"] == "length", "keep grain")
    check(new_a["article"] == new_b["article"] == "12345" and new_b["decor"] == "",
          "article for all")


def test_edge_band_tool(t):
    """Режим крайки: клік по торцю — крайка є, ще клік — немає; встановлені
    крайки підсвічено їхнім кольором; undo."""
    from core.history import History
    from core.scene import Scene
    P = importlib.import_module("ingetrazo_plugin_board_studio.panels")
    E = importlib.import_module("ingetrazo_plugin_board_studio.edgeband")
    L = importlib.import_module("ingetrazo_plugin_board_studio.library")
    scene = Scene()
    hist = History(scene)
    vp = FakeViewport(scene, hist)
    g = make_panel(t, vp, V(0, 0, 0), V(0.6, 0, 0), V(0.6, 0.4, 0))
    tool = E.EdgeBandTool()
    tool.band = L.find(L.edges(), "pvc_20")
    tool.on_activate(vp)
    check(tool.preview_faces() == [], "nothing highlighted without bands")
    p = P.Panel(g)
    side1 = next(f for f in g.mesh.faces if p.classify(f) == 1)
    top = next(f for f in g.mesh.faces if p.classify(f) == "top")

    vp.picked = top
    tool.on_click(ctx(vp, V(0, 0, 0)))
    check(P.panel_data(g)["edges"] == [0.0] * 4, "a click on the face adds nothing")

    vp.picked = side1
    tool.on_hover(ctx(vp, V(0, 0, 0)))
    check(tool.hover is not None and tool.hover[1] == 1, "hover finds the edge")
    hov = tool.preview_faces()
    check(len(hov) == 1, "hovered edge previewed")
    tool.on_click(ctx(vp, V(0, 0, 0)))
    d = P.panel_data(g)
    check(d["edges"] == [0.0, 2.0, 0.0, 0.0] and d["bands"][1]["key"] == "pvc_20",
          f"band added {d['edges']} {d['bands']}")
    faces = tool.preview_faces()
    check(len(faces) == 1 and faces[0].attrs["color"] == E.rgb("#d9534f"),
          "installed band highlighted in its colour")
    xs = {round(v.x(), 5) for v in faces[0].vertices}
    check(xs == {0.6003}, f"highlight lifted off the edge {xs}")
    check(next(f for f in g.mesh.faces if P.Panel(g).classify(f) == 1).attrs["mat"]
          != L.edges()[0]["name"], "edge repainted")

    tool.band = L.find(L.edges(), "pvc_08")    # інша крайка — заміна
    tool.on_click(ctx(vp, V(0, 0, 0)))
    check(P.panel_data(g)["edges"][1] == 0.8, "another band replaces")
    tool.on_click(ctx(vp, V(0, 0, 0)))          # той самий клік — прибрати
    d = P.panel_data(g)
    check(d["edges"] == [0.0] * 4 and d["bands"] == [None] * 4, "second click removes")
    check(tool.preview_faces() == [], "no highlight after removal")
    hist.undo()
    check(P.panel_data(g)["edges"][1] == 0.8, "undo brings the band back")


def test_drawing(t):
    """Креслення у налаштуваннях: стежить за полями, клік веде в поле, а
    розміри ті самі, що й у справжній розстановці."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QFocusEvent
    from core.history import History
    from core.scene import Scene
    L = importlib.import_module("ingetrazo_plugin_board_studio.library")
    S = importlib.import_module("ingetrazo_plugin_board_studio.settings")
    F = importlib.import_module("ingetrazo_plugin_board_studio.fasteners")
    P = importlib.import_module("ingetrazo_plugin_board_studio.panels")
    L.save(None)
    dlg = S.SettingsDialog(None)
    ed, draw = dlg.fasteners, dlg.fasteners.drawing
    for i, f in enumerate(L.fasteners()):
        ed.list.setCurrentRow(i)
        check([(h["where"], h["d"], h["depth"], h["along"]) for h in draw.holes]
              == [(h["where"], h["d"], h["depth"], h["along"]) for h in f["holes"]],
              f"drawing shows the holes of {f['name']}")
        draw.grab(), ed.placement.grab()
        check({(r, k) for _q, r, k in draw.hits} >= {(r, k) for r in range(len(f["holes"]))
                                                     for k in ("d", "depth")},
              f"every diameter and depth of {f['name']} is drawn")

    # Мініфікс: геометрія видів проти справжніх отворів на стику.
    scene = Scene()
    vp = FakeViewport(scene, History(scene))
    b_g = make_panel(t, vp, V(0, 0, 0), V(0.6, 0, 0), V(0.6, 0.4, 0))
    a_g = make_panel(t, vp, V(0.016, 0, 0.016), V(0.016, 0.4, 0.016), V(0.016, 0.4, 0.736))
    scene.selection.update([b_g, a_g])
    mini = L.fasteners()[2]
    cands, _ = F.candidates(P.selected_panels(scene), mini)
    c = cands[0]
    for h, (panel, real) in zip(draw.holes, c.holes):
        x, y = real["x"] / 1000, real["y"] / 1000
        world = panel.origin + panel.R[:, 0] * x + panel.R[:, 1] * y
        if real["type"] == "face" and panel is c.b:
            world = world + panel.R[:, 2] * (panel.size[2] if real["top"] else 0.0)
        rel = world - c.point
        x0, x1, v0, v1 = draw.plan_rect(h)
        check(abs(float(rel @ c.along) * 1000 - (v0 + v1) / 2) < 0.02, f"shift drawn {h}")
        if h["where"] == "inner_face":
            check(abs(float(rel @ c.inward) * 1000 - (x0 + x1) / 2) < 0.02, "cup inset drawn")
            check(abs(draw.section_rect(h)[3] - 8.0) < 1e-9
                  and abs(draw.section_rect(h)[2] + 5.0) < 1e-9, "cup depth from inner face")

    # Клік по розміру -> поле; фокус у полі -> підсвітка й площина перерізу.
    ed._picked(3, "along")
    check(draw.active == (3, "along") and draw.plane() == 32.0 and ed.table.currentRow() == 3,
          f"picked dimension is active {draw.active}")
    ed.eventFilter(ed.table.cellWidget(1, 2), QFocusEvent(QEvent.FocusIn))
    check(draw.active == (1, "depth"), "focused field is highlighted")
    ed.eventFilter(ed.spins["offset"], QFocusEvent(QEvent.FocusIn))
    check(draw.active[0] == -1 and ed.placement.active == (-1, "offset"),
          "focused offset is highlighted on the placement")
    hit = next(q for q, r, k in draw.hits if (r, k) == (1, "depth"))
    check(draw.hit(hit.center()) == (1, "depth"), "click on the depth label")

    # Живе оновлення й розстановка.
    ed.table.cellWidget(1, 2).setValue(0.0)
    check(draw.holes[1]["depth"] is None and ed.table.cellWidget(1, 2).text() == "наскрізь",
          "through hole")
    check(draw.section_rect(draw.holes[1])[2] == -8.0, "through hole crosses the panel")
    ed.list.setCurrentRow(1)
    pts, reason = ed.placement.points()
    check(reason == "" and pts == F.positions(720.0, 37.0, 256.0, 7.0, 64.0), f"points {pts}")
    ed.length.setValue(45.0)
    check(ed.placement.points()[0] == [] and "45 мм < 50 мм" in ed.placement.points()[1],
          "too short joint explained")
    ed.placement.grab()
    ed.thickness["B"].setValue(10.0)
    check("10 мм < 16 мм" in ed.warning.text(), f"thickness warning {ed.warning.text()}")

    # Без отворів — не падає і пояснює.
    while ed.table.rowCount():
        ed.table.setCurrentCell(0, 0)
        ed._del_row()
    draw.grab(), ed.placement.grab()
    empty = dlg.result_data()["fasteners"][1]
    check(empty["holes"] == [], "all holes deleted")
    cands, skipped = F.candidates(P.selected_panels(scene), empty)
    check(cands == [] and "жодного отвору" in skipped[0][1], "empty fastener is skipped")


def test_library_and_settings(t):
    """Налаштування: нове кріплення й крайка зберігаються в бібліотеці, панелі
    їх бачать; обмеження не пускають кріплення на тонку деталь."""
    from core.history import History
    from core.scene import Scene
    L = importlib.import_module("ingetrazo_plugin_board_studio.library")
    S = importlib.import_module("ingetrazo_plugin_board_studio.settings")
    ui = importlib.import_module("ingetrazo_plugin_board_studio.ui")
    P = importlib.import_module("ingetrazo_plugin_board_studio.panels")
    L.save(None)
    check([f["key"] for f in L.fasteners()] == ["dowel_8x30", "confirmat_7x50", "minifix_15"],
          "default fasteners")
    check(len(L.edges()) == 4, "default edge bands")
    app = SimpleNamespace(viewport=None, window=None)
    panel = ui.FastenersPanel(app)
    check(panel.list.count() == 3, "fasteners panel lists the library")

    dlg = S.SettingsDialog(None)
    ed = dlg.fasteners
    ed.list.setCurrentRow(0)
    ed.duplicate()
    ed.name.setText("Шкант 8×35")
    ed.spins["min_wall"].setValue(5.0)
    ed.table.cellWidget(0, 2).setValue(30.0)            # глибина в торці
    ed.table.cellWidget(1, 5).setText("$12345")         # артикул у пласті
    dlg.edges.add()
    dlg.edges.name.setText("ABS 1.0 дуб")
    dlg.edges.thickness.setValue(1.0)
    dlg.edges._color = "#806040"
    L.save(dlg.result_data())
    fs = L.fasteners()
    new = fs[-1]
    check(len(fs) == 4 and new["name"] == "Шкант 8×35" and new["min_wall"] == 5.0
          and new["holes"][0]["depth"] == 30.0 and new["holes"][1]["article"] == "12345"
          and new["key"] != "dowel_8x30", f"edited fastener saved {new}")
    check(L.edges()[-1]["name"] == "ABS 1.0 дуб" and L.edges()[-1]["color"] == "#806040",
          "new edge band saved")
    check(panel.list.count() == 4, "panel reloads after settings change")

    # Обмеження: стінка 5 мм під отвором 12 мм у 16-мм пласті — не можна.
    scene = Scene()
    vp = FakeViewport(scene, History(scene))
    bottom = make_panel(t, vp, V(0, 0, 0), V(0.6, 0, 0), V(0.6, 0.4, 0))
    side = make_panel(t, vp, V(0.016, 0, 0.016), V(0.016, 0.4, 0.016), V(0.016, 0.4, 0.736))
    scene.selection.update([bottom, side])
    app = SimpleNamespace(viewport=vp, window=None)
    text = ui.place_fastener(app, new["key"])
    check("не встановлено" in text and "4 мм < 5 мм" in text, f"wall constraint: {text}")
    check(P.panel_data(bottom)["holes"] == [], "nothing placed when the constraint fails")
    thin = make_panel(t, vp, V(2, 0, 0), V(2.6, 0, 0), V(2.6, 0.4, 0), thickness=0.010)
    stand = make_panel(t, vp, V(2.010, 0, 0.010), V(2.010, 0.4, 0.010), V(2.010, 0.4, 0.7))
    scene.selection.clear()
    scene.selection.update([thin, stand])
    text = ui.place_fastener(app, "confirmat_7x50")
    check("товщина 10 мм < 16 мм" in text, f"thickness constraint: {text}")
    L.save(None)
    check(panel.list.count() == 3, "defaults restored")


def main():
    QCoreApplication.setOrganizationName("board-studio-tests")
    QCoreApplication.setApplicationName("board-studio-tests")
    _app = QApplication.instance() or QApplication([])
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda _p, _t, text: FAILS.append(f"message: {text}")
                                           or print("FAIL: message:", text))
    plug, t = load_plugin()
    test_geometry(t)
    test_tool(t)
    test_panels(t)
    test_properties_dialog(t)
    test_edge_band_tool(t)
    test_drawing(t)
    test_library_and_settings(t)
    test_setup(plug, t)
    test_dialog(t)
    if FAILS:
        sys.exit(f"\n{len(FAILS)} failure(s)")
    print("OK")


if __name__ == "__main__":
    main()
