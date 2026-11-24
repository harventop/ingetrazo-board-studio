# SPDX-License-Identifier: GPL-3.0-or-later
"""Панель як деталь меблів: її локальна система, властивості (кромка,
напрямок текстури, декор Viyar), отвори і перефарбування граней.

Дані панелі лежать у ``group.ext["board_studio"]`` (зберігаються в .igz,
їдуть з копіями). Розміри й отвори — у мм, у локальній системі деталі:
X — довжина, Y — ширина, Z — товщина; сторони (торці) 0..3 — як у
:mod:`.dxf`. Локальні осі — ``group.axes`` (IngeTrazo переносить їх разом
із Move/Rotate), для старих панелей без осей — з геометрії бруска.
"""
from __future__ import annotations

import copy

import numpy as np
from PySide6.QtGui import QMatrix4x4
from PySide6.QtGui import QVector3D as V

from core.group import Group, np_affine
from core.history import Command

from .materials import PLAIN, edge_surface, ensure_materials, paint, paint_plain

EXT_KEY = "board_studio"
GRAINS = ("length", "width", "none")
TOL = 1e-4          # м: грань «лежить» на площині сторони


def panel_data(group):
    """Дані панелі з типовими значеннями (копія) або ``None``."""
    raw = (getattr(group, "ext", None) or {}).get(EXT_KEY)
    if not raw:
        return None
    data = copy.deepcopy(raw)
    data.setdefault("grain", "length")
    data.setdefault("article", "")
    data.setdefault("decor", "")
    edges = list(data.get("edges") or [])
    data["edges"] = [float(e) for e in (edges + [0.0] * 4)[:4]]
    data.setdefault("holes", [])
    bands = list(data.get("bands") or [])
    data["bands"] = (bands + [None] * 4)[:4]
    return data


def is_panel(group):
    return isinstance(group, Group) and panel_data(group) is not None


def iter_panels(scene, groups=None, base=None):
    """``(group, matrix)`` для кожної видимої панелі: матриця переводить
    сітку групи у світ (``None`` — сітка вже у світі)."""
    for g in scene.groups if groups is None else groups:
        if getattr(g, "hidden", False):
            continue
        m = g.xform
        if base is not None:
            m = base if m is None else base * m
        if is_panel(g):
            yield g, m
        yield from iter_panels(scene, g.children or (), m)


def selected_panels(scene):
    """Панелі серед виділеного; виділена група-контейнер дає всі свої панелі."""
    chosen = {id(g) for g in scene.selection if isinstance(g, Group)}
    out = []

    def walk(groups, base, inside):
        for g in groups:
            m = g.xform
            if base is not None:
                m = base if m is None else base * m
            hit = inside or id(g) in chosen
            if hit and is_panel(g) and not g.hidden:
                out.append(Panel(g, m))
            walk(g.children or (), m, hit)

    walk(scene.groups, None, False)
    # Відкрита на редагування група: її вміст — не в scene.groups.
    found = {id(p.group) for p in out}
    for g in scene.selection:
        if is_panel(g) and id(g) not in found:
            out.append(Panel(g, None))
    return out


def all_panels(scene):
    return [Panel(g, m) for g, m in iter_panels(scene)]


# ---- Локальна система -----------------------------------------------------------

def creation_axes(corners, push):
    """Осі нової панелі: X — від 1-ї до 2-ї точки, Z — бік видавлювання,
    Y = Z × X; початок — у куті, звідки всі розміри додатні."""
    x = (corners[1] - corners[0]).normalized()
    z = push.normalized()
    y = V.crossProduct(z, x).normalized()
    width = corners[3] - corners[0]
    o = corners[0] if V.dotProduct(width, y) >= 0 else corners[3]
    return QMatrix4x4(x.x(), y.x(), z.x(), o.x(),
                      x.y(), y.y(), z.y(), o.y(),
                      x.z(), y.z(), z.z(), o.z(),
                      0.0, 0.0, 0.0, 1.0)


def _qmat_frame(m):
    """QMatrix4x4 → (початок, 3×3 ортонормовані праві осі-стовпці)."""
    rot, trans = np_affine(m)
    x = rot[:, 0] / np.linalg.norm(rot[:, 0])
    y = rot[:, 1] - x * (rot[:, 1] @ x)
    y /= np.linalg.norm(y)
    z = np.cross(x, y)
    return trans, np.column_stack([x, y, z])


def _mesh_points(mesh):
    return np.array([(v.position.x(), v.position.y(), v.position.z()) for v in mesh.vertices],
                    dtype=np.float64)


def _geometry_frame(pts, data):
    """Осі зі самого бруска (старі панелі без ``axes``): три ребра з кута,
    найкоротше — товщина, довжина — те, що ближче до збереженої довжини."""
    p0 = pts[0]
    d = np.linalg.norm(pts - p0, axis=1)
    edges = []
    for i in np.argsort(d)[1:]:
        e = pts[i] - p0
        if d[i] < 1e-9:
            continue
        if all(abs(e @ f) < 1e-6 * d[i] * np.linalg.norm(f) for f in edges):
            edges.append(e)
        if len(edges) == 3:
            break
    if len(edges) < 3:
        return p0, np.eye(3)
    edges.sort(key=np.linalg.norm)
    t_edge, a, b = edges
    want = float(data.get("length") or 0.0)
    if abs(np.linalg.norm(a) - want) < abs(np.linalg.norm(b) - want):
        a, b = b, a
    x = b / np.linalg.norm(b)
    z = t_edge / np.linalg.norm(t_edge)
    y = np.cross(z, x)
    return p0, np.column_stack([x, y, z])


class Panel:
    """Панель у двох просторах: сітки (для фарбування) і світу (для
    шкантів і розкладки). Розміри — з самої геометрії, тож після Scale вони
    правильні."""

    def __init__(self, group, m=None):
        self.group, self.m = group, m
        self.data = panel_data(group)
        pts = _mesh_points(group.mesh)
        axes = getattr(group, "axes", None)
        self.has_axes = axes is not None
        o, R = _qmat_frame(axes) if axes is not None else _geometry_frame(pts, self.data)
        local = (pts - o) @ R
        lo, hi = local.min(axis=0), local.max(axis=0)
        self.size = hi - lo                                 # м: L, W, T
        self.mesh_origin, self.mesh_R = o + R @ lo, R
        if m is None:
            self.origin, self.R = self.mesh_origin, R
        else:
            rot, trans = np_affine(m)
            self.origin = rot @ self.mesh_origin + trans
            self.R = _qmat_frame(_matrix(rot @ R, self.origin))[1]

    @property
    def name(self):
        return self.group.name

    @property
    def mm(self):
        return tuple(float(v) * 1000 for v in self.size)

    def to_local_mm(self, p):
        return (np.asarray(p, dtype=np.float64) - self.origin) @ self.R * 1000

    def to_world(self, local_mm):
        return self.origin + self.R @ (np.asarray(local_mm, dtype=np.float64) / 1000)

    def mesh_axes(self):
        """``group.axes`` для цієї системи (у просторі сітки)."""
        return _matrix(self.mesh_R, self.mesh_origin)

    # ---- Грані ----
    def classify(self, face):
        """``"top"``, ``"bottom"``, номер сторони 0..3 або ``None``."""
        loc = (np.array([(p.x(), p.y(), p.z()) for p in face.vertices]) - self.mesh_origin) \
            @ self.mesh_R
        L, W, T = self.size
        for key, axis, value in (("bottom", 2, 0.0), ("top", 2, T), (0, 1, 0.0), (1, 0, L),
                                 (2, 1, W), (3, 0, 0.0)):
            if np.all(np.abs(loc[:, axis] - value) < TOL):
                return key
        return None

    def paints(self, data):
        """``[(face, attrs)]`` — як пофарбувати грані з такими властивостями:
        пласті — декор з волокнами вздовж напрямку текстури (без текстури —
        однотонний), кромковані торці — декор уздовж торця, решта торців —
        серцевина плити."""
        R = [V(*map(float, self.mesh_R[:, i])) for i in range(3)]
        x, y, z = R
        grain = data.get("grain", "length")
        core = edge_surface(data.get("material", ""))
        out = []
        for face in self.group.mesh.faces:
            key = self.classify(face)
            if key in ("top", "bottom"):
                attrs = (paint_plain() if grain == "none" else
                         paint("oak", x, y) if grain == "length" else paint("oak", y, x))
            elif key is not None:
                along = x if key in (0, 2) else y
                if data["edges"][key] > 0:
                    attrs = paint_plain() if grain == "none" else paint("oak", along, z)
                else:
                    attrs = paint(core, along, z)
            else:
                continue
            new = dict(face.attrs or {})
            for k in ("mat", "texture", "color"):
                new.pop(k, None)
            new.update(attrs)
            out.append((face, new))
        return out

    def dxf_part(self):
        from .dxf import Hole, Part
        d = self.data
        L, W, T = self.mm
        holes = []
        for h in d.get("holes", []):
            holes.append(Hole(h["type"], h["x"], h["y"], h["d"], h.get("depth"),
                              top=h.get("top", True), side=h.get("side", 0), z=h.get("z"),
                              article=h.get("article", ""), layer=h.get("layer", ""),
                              group=h.get("group") or Hole.__dataclass_fields__["group"].default))
        return Part(self.name, round(L, 2), round(W, 2), round(T, 2),
                    edges=tuple(d["edges"]), grain=d["grain"], article=d["article"],
                    decor=d["decor"], holes=holes)


def _matrix(R, o):
    return QMatrix4x4(*(float(v) for v in (R[0, 0], R[0, 1], R[0, 2], o[0],
                                          R[1, 0], R[1, 1], R[1, 2], o[1],
                                          R[2, 0], R[2, 1], R[2, 2], o[2],
                                          0.0, 0.0, 0.0, 1.0)))


# ---- Зміни з undo -----------------------------------------------------------------

class SetPanelsCommand(Command):
    """Нові дані панелей (і фарба граней, і осі) — один крок undo."""

    def __init__(self, changes):
        #: [(group, data, axes|None, [(face, attrs)])]
        self.changes = changes
        self._old = None

    def do(self, scene):
        if self._old is None:
            self._old = [(copy.deepcopy(g.ext), g.axes, [(f, f.attrs) for f, _a in paints])
                         for g, _d, _ax, paints in self.changes]
        for g, data, axes, paints in self.changes:
            ext = dict(g.ext or {})
            ext[EXT_KEY] = copy.deepcopy(data)
            g.ext = ext
            if axes is not None:
                g.axes = axes
            for f, attrs in paints:
                f.attrs = dict(attrs)
        self._touch(scene)

    def undo(self, scene):
        for (g, _d, _ax, _p), (ext, axes, paints) in zip(self.changes, self._old):
            g.ext, g.axes = ext, axes
            for f, attrs in paints:
                f.attrs = attrs
        self._touch(scene)

    @staticmethod
    def _touch(scene):
        from core.history import _dirty_group_chunks
        _dirty_group_chunks(scene)
        scene.version += 1


def update_panels(viewport, updates, repaint=True):
    """``updates``: ``[(Panel, data)]`` → один крок undo. ``repaint`` —
    перефарбувати грані за новими властивостями. Повертає помилку або None."""
    if not updates:
        return None
    if repaint:
        materials = {d.get("material", "") for _p, d in updates}
        for name in materials:
            ensure_materials(viewport.scene, name)
        if any(d.get("grain") == "none" for _p, d in updates):
            ensure_materials(viewport.scene, None, plain=True)
    changes = []
    for panel, data in updates:
        axes = None if panel.has_axes else panel.mesh_axes()
        changes.append((panel.group, data, axes, panel.paints(data) if repaint else []))
    history = viewport.history
    history.execute(SetPanelsCommand(changes))
    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    viewport.update()
    return history.last_error


__all__ = ["EXT_KEY", "GRAINS", "PLAIN", "Panel",
           "panel_data", "is_panel", "iter_panels", "selected_panels", "all_panels",
           "creation_axes", "update_panels", "SetPanelsCommand"]
