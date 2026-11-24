# SPDX-License-Identifier: GPL-3.0-or-later
"""3-Point Panel — порт ``three_point_panel_tool.rb``, ``preview_drawer.rb``
і ``geometry_helper.rb``.

Кліки: кут → довжина → висота (перпендикулярно до базової лінії). Панель
видавлюється на товщину вздовж нормалі, Ctrl перевертає бік. На кроках 2 і 3
можна набрати число й натиснути Enter. Довжини — у метрах, Z — вгору.

Це не верхній модуль плагіна, тож IngeTrazo не робить з інструмента
одноразову дію меню — його вмикає ``setup()``.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QVector3D as V

from core.axes import AXES
from core.geometry import Face
from core.group import Group
from core.history import InsertGroupCommand
from core.mesh import Mesh
from core.snap import POINT_SNAP_KINDS
from core.units import fmt_len
from tools.base import AxisMagnet, Tool, loop_normal

from .materials import DEFAULT, board_paints, ensure_materials
from .panels import EXT_KEY, creation_axes

EPS = 1e-5
SNAP_COS = math.cos(math.radians(3.0))      # висота «прилипає» до осей у межах 3°
dot, cross = V.dotProduct, V.crossProduct


# ---- Геометрія -----------------------------------------------------------------

def perp(v, u):
    """Частина ``v``, перпендикулярна до одиничного ``u``."""
    return v - u * dot(v, u)


def default_height_dir(u1):
    """«Вгору», наскільки можливо перпендикулярно до лінії (для вертикальної — Y)."""
    d = perp(V(0, 0, 1), u1)
    return (d if d.length() > 1e-6 else perp(V(0, 1, 0), u1)).normalized()


def panel_points(p1, p2, third, off_len=0.0, off_wid=0.0):
    """``(кути з відступами, вихідні кути, нормаль)`` або ``None``, якщо
    точки не дають прямокутника. Відступ — з обох боків і лише тоді, коли
    розмір більший за подвоєний відступ."""
    v1 = p2 - p1
    len1 = v1.length()
    if len1 < EPS:
        return None
    u1 = v1 / len1
    h = perp(third - p2, u1)
    len2 = h.length()
    if len2 < EPS:
        return None
    u2 = h / len2
    raw = [V(p1), V(p2), p2 + h, p1 + h]
    dl = u1 * (off_len if 0 < 2 * off_len < len1 else 0.0)
    dw = u2 * (off_wid if 0 < 2 * off_wid < len2 else 0.0)
    return [p1 + dl + dw, p2 - dl + dw, raw[2] - dl - dw, raw[3] + dl - dw], raw, cross(u1, u2)


def loop_edges(pts):
    return [(pts[i - 1], pts[i]) for i in range(len(pts))]


def box_loops(base, push):
    """Шість граней бруска, кожна обведена нормаллю назовні (замкнене тіло)."""
    top = [p + push for p in base]
    loops = [list(base), top] + [[base[i - 1], base[i], top[i], top[i - 1]] for i in range(4)]
    centre = sum(base + top, V()) / 8
    return [lp if dot(loop_normal(lp), sum(lp, V()) / 4 - centre) > 0 else lp[::-1]
            for lp in loops]


def box_edges(base, push):
    top = [p + push for p in base]
    return loop_edges(base) + loop_edges(top) + list(zip(base, top))


# ---- Інструмент ----------------------------------------------------------------

class ThreePointPanelTool(AxisMagnet, Tool):
    name = "3-Point Panel"
    icon = "rectangle"          # курсор-олівець із прямокутником
    description = ("Create a panel of the set thickness from three points: "
                   "corner, length, height.")
    STEPS = ("Click first corner",
             "Click second point (length), or type the length",
             "Click third point (height), or type the height")

    def __init__(self, thickness=0.016, offset_length=0.0, offset_width=0.0,
                 material=DEFAULT):
        self.material = material        # назва плити з materials.PRESETS
        self.thickness = thickness
        self.offset_length = offset_length
        self.offset_width = offset_width
        self.flip = False
        self.hover = None
        self._ctrl = False
        self._reset()

    def _reset(self):
        self.points = []
        self.work_plane = None      # площину грані під першим кліком ставить viewport

    # ---- Що читає viewport ----
    @property
    def start_point(self):
        return self.points[0] if self.points else None

    @property
    def vcb_label(self):
        return "Height" if len(self.points) == 2 else "Length"

    def magnet_on(self):
        return len(self.points) == 1        # магніт осей — лише для базової лінії

    @property
    def diagonal_span(self):
        return len(self.points) == 2

    def drag_plane(self, viewport):
        """Крок висоти: площина через базову лінію, повернута до камери, —
        промінь курсора її завжди перетинає (і над горизонтом теж)."""
        if len(self.points) < 2:
            return None
        cam = viewport.camera
        side = perp(cam.target - cam.eye(), self._u1())
        return (self.points[1], side.normalized()) if side.length() > 1e-6 else None

    # ---- Життєвий цикл ----
    def on_activate(self, viewport):
        self._reset()
        self._prompt(viewport)

    def on_deactivate(self, viewport):
        self._reset()

    def on_cancel(self, viewport):
        self.on_activate(viewport)
        viewport.update()

    # ---- Миша ----
    def on_hover(self, ctx):
        self.hover = self._height_cursor(ctx) if len(self.points) == 2 else V(ctx.world)
        ctx.viewport.update()

    def on_click(self, ctx):
        if len(self.points) == 2:
            self._finish(ctx.viewport, self._height_cursor(ctx))
        elif not self.points or (ctx.world - self.points[0]).length() >= EPS:
            self._add_point(ctx.viewport, V(ctx.world))

    def on_value(self, viewport, value):
        """Набране число + Enter: довжина на кроці 2, висота на кроці 3."""
        if isinstance(value, tuple) or not self.points or value == 0:
            return False
        if len(self.points) == 1:
            p1 = self.points[0]
            d = self.hover - p1 if self.hover is not None else V()
            self._add_point(viewport, p1 + (d.normalized() if d.length() > EPS else V(1, 0, 0)) * value)
        else:
            self._finish(viewport, self.points[1] + self._height_dir() * value)
        return True

    # ---- Ctrl: перемикаємо одразу; якщо це був Ctrl+Z тощо — вертаємо на відпусканні ----
    def on_key(self, viewport, key, modifiers):
        if key != Qt.Key_Control:
            return False
        self._toggle_flip(viewport)
        self._ctrl = True
        return True

    def on_key_release(self, viewport, key):
        if key != Qt.Key_Control or not self._ctrl:
            return False
        self._ctrl = False
        if not self.ctrl_tapped(viewport):
            self._toggle_flip(viewport)
        return True

    def status_clause(self):
        return f"Ctrl = flip push direction {self._side()}"

    # ---- Прев'ю ----
    def rubber_band_lines(self):
        if not self.points or self.hover is None:
            return []
        lines = [(self.points[0], self.points[1] if len(self.points) == 2 else self.hover)]
        panel = self._panel()
        if panel:
            lines += box_edges(panel[0], panel[2])
        return lines

    def guide_preview_lines(self):
        """Пунктиром — вихідний габарит, коли задано відступи."""
        panel = self._panel()
        return loop_edges(panel[1]) if panel and (self.offset_length or self.offset_width) else []

    def preview_faces(self):
        panel = self._panel()
        if not panel:
            return []
        corners, _raw, push = panel
        return [Face(vertices=lp, attrs=attrs) for lp, attrs in
                zip(box_loops(corners, push), board_paints(corners, push, self.material))]

    def value_label(self):
        if not self.points or self.hover is None:
            return None
        a = self.points[-1]
        d = self.hover - a if len(self.points) == 1 else perp(self.hover - a, self._u1())
        return fmt_len(d.length()), (a + self.hover) * 0.5

    # ---- Внутрішнє ----
    def _u1(self):
        return (self.points[1] - self.points[0]).normalized()

    def _side(self):
        return "[-]" if self.flip else "[+]"

    def _panel(self, third=None):
        """``(кути, вихідні кути, вектор видавлювання)`` для третьої точки (типово — курсора)."""
        third = self.hover if third is None else third
        if len(self.points) < 2 or third is None:
            return None
        res = panel_points(*self.points, third, self.offset_length, self.offset_width)
        if res is None:
            return None
        corners, raw, normal = res
        return corners, raw, normal * (-self.thickness if self.flip else self.thickness)

    def _height_dir(self):
        u1 = self._u1()
        h = perp(self.hover - self.points[1], u1) if self.hover is not None else V()
        return h.normalized() if h.length() > EPS else default_height_dir(u1)

    def _height_cursor(self, ctx):
        """Куди вказує курсор для висоти. Прив'язку до точки моделі беремо як є.
        Інакше промінь курсора перетинаємо з площиною, перпендикулярною до
        базової лінії через другу точку (висота може піти в будь-який бік
        навколо лінії); далі — блокування осі стрілками або «прилипання» до осей."""
        if getattr(ctx.snap, "kind", None) in POINT_SNAP_KINDS:
            return V(ctx.world)
        p2, u1 = self.points[1], self._u1()
        cursor = V(ctx.world)
        origin, ray = ctx.viewport._pixel_to_ray(ctx.screen.x(), ctx.screen.y())
        if ray is not None and abs(dot(ray, u1)) > 0.05:
            t = dot(p2 - origin, u1) / dot(ray, u1)
            if t > 0:
                cursor = origin + ray * t
        h = perp(cursor - p2, u1)

        lock = getattr(ctx.viewport, "axis_lock", None)
        if lock in AXES:                                # стрілка: строго вздовж осі
            a = perp(V(AXES[lock]), u1)
            if a.length() > 1e-6:
                a = a.normalized()
                return p2 + a * dot(h, a)
        axes = list(AXES.values()) + ([self.work_plane[1]] if self.work_plane is not None else [])
        for a in axes:
            a = perp(V(a), u1)
            if a.length() > 1e-3 and h.length() > EPS:
                a = a.normalized()
                c = dot(h, a)
                if abs(c) >= SNAP_COS * h.length():
                    return p2 + a * math.copysign(h.length(), c)
        return p2 + h

    def _add_point(self, viewport, p):
        self.points.append(p)
        self._prompt(viewport)
        viewport.update()

    def _finish(self, viewport, third):
        panel = self._panel(third)
        if panel is None:
            viewport.flash_status("The height is zero — move away from the base line, "
                                  "or type the height and press Enter", 4000)
            return
        self._create(viewport, panel[0], panel[2])
        self.on_cancel(viewport)

    def _toggle_flip(self, viewport):
        self.flip = not self.flip
        self._prompt(viewport)
        viewport.update()

    def _prompt(self, viewport):
        viewport.flash_status(f"{self.STEPS[len(self.points)]} {self._side()} | "
                              "Ctrl = flip push direction", 10000)
        self.refresh_hint(viewport)

    def _create(self, viewport, corners, push):
        """Окрема група з бруском, один крок undo. ``InsertGroupCommand`` кладе
        її у відкриту на редагування групу, якщо є (як ``active_entities``)."""
        ensure_materials(viewport.scene, self.material)
        mesh = Mesh()
        for lp, attrs in zip(box_loops(corners, push), board_paints(corners, push, self.material)):
            mesh.add_face(lp).attrs = attrs
        group = Group(mesh, name=_next_name(viewport.scene))
        group.axes = creation_axes(corners, push)      # X — довжина, Z — товщина
        sizes = {"length": (corners[1] - corners[0]).length(),
                 "width": (corners[3] - corners[0]).length(),
                 "thickness": push.length(),
                 "offset_length": self.offset_length,
                 "offset_width": self.offset_width}
        group.ext = {EXT_KEY: {"material": self.material,
                               **{k: round(v, 6) for k, v in sizes.items()},
                               "grain": "length", "article": "", "decor": "",
                               "edges": [0.0] * 4, "holes": []}}
        history = viewport.history
        history.execute(InsertGroupCommand(group))
        if history.last_error:
            viewport.flash_status(f"Panel was not created: {history.last_error}", 6000)
        notify = getattr(viewport, "notify_scene_changed", None)
        if callable(notify):
            notify()


def _names(groups):
    for g in groups:
        yield g.name
        yield from _names(g.children)


def _next_name(scene):
    taken = set(_names(scene.groups))
    k = 1
    while f"Panel {k}" in taken:
        k += 1
    return f"Panel {k}"
