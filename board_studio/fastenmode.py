# SPDX-License-Identifier: GPL-3.0-or-later
"""Режим «Кріплення»: працює разом із панеллю «Кріплення».

- Клік біля рекомендованого місця (пунктирне кільце) — відмітити його або
  зняти відмітку; «Додати» в панелі ставить відмічені.
- Клік по панелі — додати її до виділення або прибрати з нього: так можна
  обрати пару панелей, не виходячи з режиму.
"""
from __future__ import annotations

from tools.base import Tool

from .i18n import tr
from .panels import iter_panels


class FastenerTool(Tool):
    icon = "select"
    uses_snap = False

    def __init__(self, panel_getter):
        self._panel = panel_getter      # → FastenersPanel або None

    @property
    def name(self):
        return tr("Fasteners")

    @property
    def description(self):
        return tr("Click a suggested place to mark it for the fastener; "
                  "click a panel to add it to the selection or remove it.")

    def on_activate(self, viewport):
        viewport.flash_status(tr("Fasteners: click a suggested place to mark it, "
                                 "click a panel to select it"), 10000)
        refresh = getattr(self, "refresh_hint", None)
        if callable(refresh):
            refresh(viewport)

    def on_deactivate(self, viewport):
        viewport.update()

    def on_cancel(self, viewport):
        panel = self._panel()
        if panel is not None:
            panel.set_checked(set())        # Esc — зняти відмітки
        viewport.update()

    def on_hover(self, ctx):
        pass

    def on_click(self, ctx):
        vp = ctx.viewport
        x, y = ctx.screen.x(), ctx.screen.y()
        panel = self._panel()
        if panel is not None:
            key = panel.pick(vp, x, y)
            if key is not None:
                panel.toggle(key)
                return
        group = self._panel_under(vp, x, y)
        if group is None:
            return
        sel = vp.scene.selection
        if group in sel:
            sel.discard(group)
        else:
            sel.add(group)
        vp.scene.version += 1
        notify = getattr(vp, "notify_scene_changed", None)
        if callable(notify):
            notify()
        vp.update()

    @staticmethod
    def _panel_under(vp, x, y):
        """Панель під курсором; вкладену у контейнер — сам контейнер
        (виділяти можна лише те, що на поточному рівні)."""
        face, owner = vp.pick_face_any(x, y)
        if face is None:
            return None
        top = {id(g) for g in vp.scene.groups}
        for g, _m in iter_panels(vp.scene):
            if any(f is face for f in g.mesh.faces):
                return g if id(g) in top else owner
        return owner
