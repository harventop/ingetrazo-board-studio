# SPDX-License-Identifier: GPL-3.0-or-later
"""Режим «Крайка»: клік по торцю панелі — додати обрану крайку, ще клік —
прибрати. Поки режим увімкнено, всі встановлені крайки підсвічено їхнім
кольором (грані попереднього перегляду, з глибиною — як у Push/Pull), а
торець під курсором показує, що станеться після кліку.

Крайка панелі — ``data["bands"][side]`` (знімок із бібліотеки: ключ, назва,
колір, товщина) і ``data["edges"][side]`` — товщина для DXF.
"""
from __future__ import annotations

import copy

from PySide6.QtGui import QColor
from PySide6.QtGui import QVector3D as V

from core.geometry import Face
from tools.base import Tool, loop_normal

from .panels import Panel, iter_panels, panel_data, update_panels

LIFT = 0.3          # мм: підсвітка трохи над торцем, щоб не мерехтіла з ним
OLD_BAND = "#9a9a9a"    # крайка без запису в бібліотеці (зі старих версій)


def rgb(color):
    c = QColor(color)
    return [c.redF(), c.greenF(), c.blueF()]


def band_snapshot(band):
    return {k: band.get(k) for k in ("key", "name", "color", "thickness")}


def side_quad(panel, side, lift=LIFT):
    """Чотири світові точки торця ``side``, трохи винесені назовні; обхід —
    нормаллю назовні."""
    L, W, T = panel.mm
    corners = {0: [(0, -lift), (L, -lift)], 1: [(L + lift, 0), (L + lift, W)],
               2: [(L, W + lift), (0, W + lift)], 3: [(-lift, W), (-lift, 0)]}[side]
    (x0, y0), (x1, y1) = corners
    pts = [panel.to_world(p) for p in ((x0, y0, 0), (x1, y1, 0), (x1, y1, T), (x0, y0, T))]
    loop = [V(*map(float, p)) for p in pts]
    centre = panel.to_world((L / 2, W / 2, T / 2))
    mid = sum(loop, V()) / 4
    if V.dotProduct(loop_normal(loop), mid - V(*map(float, centre))) < 0:
        loop.reverse()
    return loop


class EdgeBandTool(Tool):
    name = "Edge Banding"
    icon = "paint"
    description = "Click an edge of a panel to add the chosen edge band; click again to remove it."
    uses_snap = False

    def __init__(self):
        self.band = None            # словник із бібліотеки
        self.hover = None           # (Panel, side)
        self._faces = None          # кеш: id(face) → (group, matrix)
        self._faces_key = None

    # ---- Життєвий цикл ----
    def on_activate(self, viewport):
        self._viewport = viewport           # preview_faces() питає без аргументів
        self.hover = None
        self._prompt(viewport)
        viewport.update()

    def on_deactivate(self, viewport):
        self.hover = None
        viewport.update()

    def on_cancel(self, viewport):
        self.hover = None
        viewport.update()

    # ---- Пошук торця ----
    def _face_index(self, scene):
        key = (id(scene), scene.version)
        if key != self._faces_key:
            self._faces = {id(f): (g, m) for g, m in iter_panels(scene) for f in g.mesh.faces}
            self._faces_key = key
        return self._faces

    def pick(self, viewport, x, y):
        """``(Panel, side)`` під курсором або ``None``."""
        face, _owner = viewport.pick_face_any(x, y)
        if face is None:
            return None
        hit = self._face_index(viewport.scene).get(id(face))
        if hit is None:
            return None
        panel = Panel(*hit)
        side = panel.classify(face)
        return (panel, side) if isinstance(side, int) else None

    # ---- Миша ----
    def on_hover(self, ctx):
        self._viewport = ctx.viewport
        hover = self.pick(ctx.viewport, ctx.screen.x(), ctx.screen.y())
        if (hover is None) != (self.hover is None) or (
                hover and self.hover and (hover[0].group is not self.hover[0].group
                                          or hover[1] != self.hover[1])):
            self.hover = hover
            ctx.viewport.update()

    def on_click(self, ctx):
        vp = ctx.viewport
        hit = self.pick(vp, ctx.screen.x(), ctx.screen.y())
        if hit is None:
            vp.flash_status("Click an edge of a Board Studio panel", 3000)
            return
        if self.band is None:
            vp.flash_status("Choose an edge band in the Крайка panel", 4000)
            return
        panel, side = hit
        data = copy.deepcopy(panel.data)
        current = data["bands"][side]
        if current is not None and current.get("key") == self.band.get("key"):
            data["bands"][side] = None
            data["edges"][side] = 0.0
            text = f"{self.band['name']} removed"
        else:
            data["bands"][side] = band_snapshot(self.band)
            data["edges"][side] = float(self.band["thickness"])
            text = f"{self.band['name']} added"
        err = update_panels(vp, [(panel, data)])
        vp.flash_status(f"Edge band not changed: {err}" if err else
                        f"{panel.name}: {text}", 3000)
        self.hover = None
        vp.update()

    # ---- Підсвітка ----
    def preview_faces(self):
        vp = getattr(self, "_viewport", None)
        return self.highlight_faces(vp.scene) if vp is not None else []

    def highlight_faces(self, scene):
        """Грані підсвітки; перераховуються лише коли змінився документ,
        торець під курсором або обрана крайка (preview_faces — щокадру)."""
        hover = (id(self.hover[0].group), self.hover[1]) if self.hover else None
        key = (id(scene), scene.version, hover, (self.band or {}).get("key"),
               (self.band or {}).get("color"))
        if key != getattr(self, "_hl_key", None):
            self._hl_key, self._hl = key, self._highlight(scene)
        return self._hl

    def _highlight(self, scene):
        faces = []
        for g, m in iter_panels(scene):
            panel = None
            data = panel_data(g)
            for side in range(4):
                band = data["bands"][side]
                hovered = (self.hover is not None and self.hover[0].group is g
                           and self.hover[1] == side)
                if band is None and not data["edges"][side] and not hovered:
                    continue
                panel = panel or Panel(g, m)
                if hovered:
                    color = self._hover_color(band)
                else:
                    color = rgb((band or {}).get("color") or OLD_BAND)
                faces.append(Face(vertices=side_quad(panel, side), attrs={"color": color}))
        return faces

    def _hover_color(self, band):
        if self.band is None:
            return [0.6, 0.6, 0.6]
        if band is not None and band.get("key") == self.band.get("key"):
            return [0.55, 0.55, 0.55]           # клік прибере
        c = rgb(self.band["color"])
        return [0.5 + v / 2 for v in c]         # клік додасть — світліший колір

    def _prompt(self, viewport):
        name = self.band["name"] if self.band else "—"
        viewport.flash_status(f"Edge band {name}: click an edge to add, click again to remove",
                              10000)
        refresh = getattr(self, "refresh_hint", None)
        if callable(refresh):
            refresh(viewport)
