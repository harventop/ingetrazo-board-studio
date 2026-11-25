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
import math

import numpy as np
from PySide6.QtGui import QMatrix4x4
from PySide6.QtGui import QVector3D as V

from core.group import Group, np_affine
from core.history import Command

from . import outline
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
    data.setdefault("extra_bands", [])      # крайка дуг і скосів, див. Panel.bands
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
        self._outline, self.cutouts, self._material = None, 0, []
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

    # ---- Контур ----
    def outline(self):
        """Ділянки контуру (:class:`.outline.Segment`, локальні мм, проти стрілки)
        або ``[]``, якщо пласть не вдалось прочитати."""
        if self._outline is None:
            self._outline, self.cutouts, self._material = [], 0, []
            for key in ("top", "bottom"):
                loops = self._loops(key)
                if loops:
                    self._outline = outline.segments(*loops[0], *self.mm[:2])
                    self.cutouts = len(loops) - 1
                    if self.cutouts or not outline.is_box(self._outline):
                        outer = [p for s in self._outline for p in s.fine()[:-1]]
                        self._material = [outer] + [pts for pts, _s, _c in loops[1:]]
                    break
        return self._outline

    @property
    def is_box(self):
        """Прямокутна деталь (або контур не прочитано — тоді за габаритом)."""
        segs = self.outline()
        return not segs or outline.is_box(segs)

    def material(self):
        """Ламані контуру й вирізів (локальні мм) або ``[]``, якщо деталь — цілий
        прямокутник."""
        self.outline()
        return self._material

    def side_spans(self, side):
        """Прямі ділянки торця ``side`` (мм від його початку, як у
        :func:`.joints.side_frame`): без заокруглень, скосів і вирізів."""
        segs = self.outline()
        if not self.material():
            return [(0.0, self.mm[0 if side in (0, 2) else 1])]
        axis = 0 if side in (0, 2) else 1
        return sorted(tuple(sorted((s.pts[0][axis], s.pts[-1][axis])))
                      for s in segs if s.side == side)

    def _loops(self, key):
        """Межі пласті ``key``: ``[(точки, гладкі, криві)]``, зовнішня — перша;
        ``[]``, якщо пласть менша за габарит (напр. заокруглено ребро пласті)."""
        mesh = self.group.mesh
        nxt, edges = {}, set()
        for face in mesh.faces:
            if self.classify(face) != key:
                continue
            up = self.mesh_R[:, 2] if key == "top" else -self.mesh_R[:, 2]
            n = face.normal()
            same = float(np.array([n.x(), n.y(), n.z()]) @ up) > 0
            for k, loop in enumerate([face.loop] + face.hole_loops):
                loop = list(loop)
                # Нормаль може дивитись і всередину; вирізи — у зворотний бік.
                if k and self._area(loop) * self._area(face.loop) > 0:
                    loop.reverse()
                if not same:
                    loop.reverse()
                for a, b in zip(loop, loop[1:] + loop[:1]):
                    if (id(b), id(a)) in edges:         # спільне ребро двох граней
                        edges.discard((id(b), id(a)))
                    else:
                        edges.add((id(a), id(b)))
                    nxt[id(a)], nxt[id(b)] = a, b
        follow = dict(edges)
        out = []
        while follow:
            a = next(iter(follow))
            chain = []
            while a in follow:
                chain.append(nxt[a])
                a = follow.pop(a)
            if len(chain) > 2:
                out.append(chain)
        out.sort(key=lambda c: -abs(self._area(c)))
        if not out:
            return []
        pts = np.array(self._xy(out[0]))
        if np.abs(pts.min(axis=0)).max() > 0.1 \
                or np.abs(pts.max(axis=0) - np.array(self.mm[:2])).max() > 0.1:
            return []
        result = []
        for chain in out:
            if self._area(chain) < 0:
                chain.reverse()
            links = [mesh.find_edge(a, b) for a, b in zip(chain, chain[1:] + chain[:1])]
            result.append(([tuple(p) for p in self._xy(chain)],
                           [self._smooth(v) for v in chain],
                           [getattr(e, "curve", None) if e else None for e in links]))
        return result

    def _xy(self, verts):
        """Вершини сітки → локальні (x, y), мм."""
        pts = np.array([(v.position.x(), v.position.y(), v.position.z()) for v in verts])
        return ((pts - self.mesh_origin) @ self.mesh_R * 1000)[:, :2].tolist()

    def _area(self, verts):
        return outline.area([tuple(p) for p in self._xy(verts)])

    def _smooth(self, v):
        """Чи м'яке вертикальне ребро у вершині пласті."""
        z = self.mesh_R[:, 2]
        for e in self.group.mesh.edges_at(v):
            d = e.other(v).position - v.position
            d = np.array([d.x(), d.y(), d.z()])
            if abs(d @ z) > 0.999 * np.linalg.norm(d):
                return bool(getattr(e, "soft", False))
        return False

    def edge_segment(self, face):
        """Ділянка контуру, якій належить торцева грань, і чи це її частина:
        ``(Segment, номер відрізка)`` або ``None``."""
        pts = self._face_xy(face)
        if pts is None:
            return None
        p, q = pts
        for seg in self.outline():
            for k, (a, b) in enumerate(zip(seg.pts, seg.pts[1:])):
                d = math.dist(a, b)
                if d < 1e-9:
                    continue
                t = (b[0] - a[0]) / d, (b[1] - a[1]) / d
                if all(abs((x - a[0]) * t[1] - (y - a[1]) * t[0]) < 0.1
                       and -0.1 <= (x - a[0]) * t[0] + (y - a[1]) * t[1] <= d + 0.1
                       for x, y in (p, q)):
                    return seg, k
        return None

    def _face_xy(self, face):
        """Вертикальна грань → її два кінці (x, y), мм, або ``None``."""
        pts = [tuple(p) for p in self._xy(face.loop)] if hasattr(face, "loop") else []
        if len(pts) < 3:
            return None
        a = pts[0]
        b = max(pts, key=lambda p: math.dist(a, p))
        a = max(pts, key=lambda p: math.dist(b, p))
        d = math.dist(a, b)
        if d < 0.05 or any(abs((x - a[0]) * (b[1] - a[1]) - (y - a[1]) * (b[0] - a[0])) / d
                           > 0.1 for x, y in pts):
            return None
        return a, b

    def edge_key(self, face):
        """Торець для крайки: сторона 0..3, ``("x", n)`` — дуга чи скіс n-ї ділянки
        контуру, або ``None``."""
        key = self.classify(face)
        if isinstance(key, int) or key is not None:
            return key if isinstance(key, int) else None
        hit = self.edge_segment(face)
        return hit[0].key if hit else None

    # ---- Крайка ----
    # Сторони 0..3 — ``data["bands"]`` і ``data["edges"]``. Дуги й скоси —
    # ``data["extra_bands"]``: крайка з місцем середини ділянки відносно
    # найближчого кута деталі (переживає зміну розмірів і радіуса).
    def _extra(self):
        return [s for s in self.outline() if s.side is None]

    def _corner(self, p):
        L, W, _T = self.mm
        cx, cy = int(p[0] > L / 2), int(p[1] > W / 2)
        return [cx, cy, round(p[0] - cx * L, 2), round(p[1] - cy * W, 2)]

    def bands(self, data=None):
        """``{ключ торця: (крайка | None, товщина)}`` — лише кромковані."""
        data = self.data if data is None else data
        out = {}
        for s in range(4):
            if data["bands"][s] is not None or data["edges"][s]:
                out[s] = data["bands"][s], data["edges"][s]
        if not data["extra_bands"]:
            return out
        L, W, _T = self.mm
        pairs = []
        for seg in self._extra():
            mid = seg.middle()[0]
            for i, e in enumerate(data["extra_bands"]):
                cx, cy, dx, dy = e["at"]
                d = math.dist(mid, (cx * L + dx, cy * W + dy))
                if d <= max(1.0, seg.length / 2):
                    pairs.append((d, i, seg.key, e))
        used = set()
        for _d, i, key, e in sorted(pairs, key=lambda p: p[:2]):
            if i not in used and key not in out:
                used.add(i)
                out[key] = e.get("band"), float(e.get("thickness") or 0.0)
        return out

    def set_band(self, data, key, band, thickness):
        """Записати крайку торця ``key`` у ``data`` (``band`` None — прибрати)."""
        if isinstance(key, int):
            data["bands"][key], data["edges"][key] = band, float(thickness)
            return
        have = {k: v for k, v in self.bands(data).items() if not isinstance(k, int)}
        have.pop(key, None)
        if band is not None:
            have[key] = band, float(thickness)
        data["extra_bands"] = [
            {"at": self._corner(s.middle()[0]), "band": have[s.key][0],
             "thickness": have[s.key][1]} for s in self._extra() if s.key in have]

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
        out, bands = [], self.bands(data)
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
                attrs = self._paint_extra(face, bands, grain, core)
                if attrs is None:
                    continue
            new = dict(face.attrs or {})
            for k in ("mat", "texture", "color"):
                new.pop(k, None)
            new.update(attrs)
            out.append((face, new))
        return out

    def _paint_extra(self, face, bands, grain, core):
        """Фарба грані дуги чи скосу: текстура йде вздовж контуру без розривів."""
        hit = self.edge_segment(face)
        if hit is None:
            return None
        seg, k = hit
        banded = bands.get(seg.key, (None, 0.0))[1] > 0
        if banded and grain == "none":
            return paint_plain()
        a, b = seg.pts[k], seg.pts[k + 1]
        d = math.dist(a, b)
        along = self.mesh_R @ np.array([(b[0] - a[0]) / d, (b[1] - a[1]) / d, 0.0])
        attrs = paint("oak" if banded else core, V(*map(float, along)),
                      V(*map(float, self.mesh_R[:, 2])))
        start = self.mesh_origin + self.mesh_R @ np.array([a[0], a[1], 0.0]) / 1000
        before = sum(math.dist(p, q) for p, q in zip(seg.pts[:k], seg.pts[1:k + 1])) / 1000
        tex = attrs["texture"]
        tex["uvw"][3] = float(before - along @ start) / tex["sw"]
        return attrs

    def dxf_part(self):
        from .dxf import Edge, Hole, Part
        d = self.data
        L, W, T = self.mm
        holes = []
        for h in d.get("holes", []):
            holes.append(Hole(h["type"], h["x"], h["y"], h["d"], h.get("depth"),
                              top=h.get("top", True), side=h.get("side", 0), z=h.get("z"),
                              article=h.get("article", ""), layer=h.get("layer", ""),
                              group=h.get("group") or Hole.__dataclass_fields__["group"].default))
        shape = []
        if not self.is_box:
            bands = self.bands()
            for s in self.outline():
                pts = [(round(x, 3), round(y, 3)) for x, y in s.fine()]
                shape.append(Edge(pts, *s.middle(), bands.get(s.key, (None, 0.0))[1]))
            for e, after in zip(shape, shape[1:] + shape[:1]):
                after.pts[0] = e.pts[-1]        # стик без щілин
        return Part(self.name, round(L, 2), round(W, 2), round(T, 2),
                    edges=tuple(d["edges"]), grain=d["grain"], article=d["article"],
                    decor=d["decor"], holes=holes, outline=shape)


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
