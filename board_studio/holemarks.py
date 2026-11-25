# SPDX-License-Identifier: GPL-3.0-or-later
"""Позначки отворів у видовому вікні.

Отвір малюється справжнім розміром на тій стороні панелі, де він є:

- устя видно — суцільний контур із заливкою;
- отвір усередині (устя з зворотного боку, у стику, під сусідньою деталлю) —
  пунктиром, разом із контуром глибини;
- отвір за іншою, сторонньою панеллю — не малюється.

Накладка малюється поверх кадру і глибини не має, тож видимість рахується
тут: промінь від ока до кожної точки контуру проти брусків усіх видимих
панелей. «Своїми» для отвору є панелі, що торкаються його устя або дна: вони
отвір містять, тож роблять його «внутрішнім», а не схованим.
"""
from __future__ import annotations

from collections import namedtuple

import numpy as np
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QColor, QPen, QPolygonF

from .fastenmode import FastenerTool
from .joints import hole_world
from .panels import all_panels

VISIBLE, INSIDE, HIDDEN = 0, 1, 2
RING = 24               # відрізків у колі
LINE = 4                # відрізків у твірній циліндра
TOUCH = 0.0005          # м: панель торкається точки
DEPTH = 0.0002          # м: стільки променя має пройти крізь панель, щоб вона закрила
SMALL = 2.5             # px: дрібніший отвір — крапка

#: Звідки дивимось: ``eye`` — None у паралельній проєкції; ``cut`` — (n, d)
#: активного розрізу (сховане — де n·p > d); ``xray`` — панелі нічого не ховають.
View = namedtuple("View", "eye forward cut xray")


#: Коли показувати кріплення в моделі (налаштування, спільне для документів).
SETTING = "board_studio/show_fasteners"
ALWAYS, IN_MODE = "always", "mode"
_show = None


def show_when():
    global _show
    if _show is None:
        _show = IN_MODE if str(QSettings().value(SETTING, ALWAYS)) == IN_MODE else ALWAYS
    return _show


def set_show_when(value):
    global _show
    _show = value
    QSettings().setValue(SETTING, value)


def shown_in(viewport):
    """Чи показувати зараз кріплення: завжди або лише в режимі «Кріплення»."""
    return show_when() == ALWAYS or isinstance(getattr(viewport, "active_tool", None),
                                               FastenerTool)


def _vec(v):
    return np.array([v.x(), v.y(), v.z()], dtype=np.float64)


def view_of(viewport):
    cam = viewport.camera
    eye = _vec(cam.eye()) if getattr(cam, "perspective", True) else None
    cut = None
    scene = viewport.scene
    if getattr(scene, "show_section_cuts", True):
        plane = scene.active_section() if callable(getattr(scene, "active_section", None)) else None
        if plane is not None:
            n = _vec(plane.normal)
            cut = (n, float(n @ _vec(plane.point)))
    style = getattr(viewport, "_effective_style", None)
    xray = bool(style and style().face_mode in ("xray", "wireframe"))
    return View(eye, _vec(cam.forward()), cut, xray)


def _view_key(view):
    cut = None if view.cut is None else (tuple(view.cut[0]), view.cut[1])
    return (None if view.eye is None else tuple(view.eye), tuple(view.forward), cut, view.xray)


class Boxes:
    """Бруски панелей як перешкоди для променів."""

    def __init__(self, panels):
        self.origin = np.array([p.origin for p in panels], dtype=np.float64).reshape(-1, 3)
        self.R = np.array([p.R for p in panels], dtype=np.float64).reshape(-1, 3, 3)
        self.size = np.array([p.size for p in panels], dtype=np.float64).reshape(-1, 3)

    def touch(self, pts):
        """(N, 3) → (N, M): чи точка в бруску або на його поверхні."""
        loc = np.einsum("nmi,mij->nmj", pts[:, None] - self.origin, self.R)
        return np.all((loc >= -TOUCH) & (loc <= self.size + TOUCH), axis=2)

    @staticmethod
    def _span(o, d, lo, hi):
        """Частина променя o + d·t у бруску [lo, hi]: (t входу, t виходу)."""
        with np.errstate(divide="ignore", invalid="ignore"):
            a, b = (lo - o) / d, (hi - o) / d
        t0, t1 = np.minimum(a, b), np.maximum(a, b)
        flat = np.abs(d) < 1e-12            # промінь уздовж площини: у смузі або ні
        out = (o < lo) | (o > hi)
        t0 = np.where(flat, np.where(out, np.inf, -np.inf), t0)
        t1 = np.where(flat, np.where(out, -np.inf, np.inf), t1)
        return t0.max(axis=-1), t1.min(axis=-1)

    @staticmethod
    def _origins(view, pts):
        return pts - view.forward * 1000.0 if view.eye is None \
            else np.broadcast_to(view.eye, pts.shape)

    def status(self, view, pts, own):
        """Видимість точок ``pts`` (N, S, 3) предметів, для яких панелі
        ``own`` (N, M) — свої: (N, S) із VISIBLE / INSIDE / HIDDEN."""
        n, s = pts.shape[:2]
        out = np.full((n, s), VISIBLE)
        start = np.zeros((n, s))
        eyes = self._origins(view, pts)
        if view.cut is not None:
            normal, level = view.cut
            side, side_eye = pts @ normal - level, eyes @ normal - level
            # Те, що розріз прибрав, нічого не закриває: промінь — від площини.
            with np.errstate(divide="ignore", invalid="ignore"):
                start = np.where(side_eye > 0, side_eye / (side_eye - side), 0.0)
            start = np.where(np.isfinite(start), np.clip(start, 0.0, 1.0), 0.0)
        if n and len(self.size):
            rows, cols = self._pairs(view, pts)
            dist = np.linalg.norm(pts - eyes, axis=2)[rows]
            R = self.R[cols]
            o = np.einsum("psi,pij->psj", eyes[rows] - self.origin[cols][:, None], R)
            d = np.einsum("psi,pij->psj", (pts - eyes)[rows], R)
            t0, t1 = self._span(o, d, np.zeros(3), self.size[cols][:, None])
            length = (np.minimum(t1, 1.0) - np.maximum(t0, start[rows])) * dist
            mark = np.where(own[rows, cols], INSIDE, INSIDE if view.xray else HIDDEN)
            np.maximum.at(out, rows, np.where(length > DEPTH, mark[:, None], VISIBLE))
        if view.cut is not None:
            out[side > 1e-6] = HIDDEN
        return out

    def _pairs(self, view, pts):
        """Пари (предмет, панель), де панель узагалі може щось закрити: промінь
        у середину предмета проти бруска, збільшеного на його радіус."""
        mid = pts.mean(axis=1)
        r = np.linalg.norm(pts - mid[:, None], axis=2).max(axis=1)[:, None, None] + 1e-4
        eyes = self._origins(view, mid)
        o = np.einsum("nmi,mij->nmj", eyes[:, None] - self.origin, self.R)
        d = np.einsum("ni,mij->nmj", mid - eyes, self.R)
        t0, t1 = self._span(o, d, -r, self.size + r)
        return np.nonzero((t1 >= t0) & (t1 >= 0.0) & (t0 <= 1.0))


class SceneBoxes:
    """Видимі панелі сцени і їхні бруски; перераховуються зі зміною документа."""

    def __init__(self):
        self._key = None
        self.panels, self.boxes = [], Boxes([])

    def update(self, scene):
        """``True``, якщо список перераховано."""
        key = (id(scene), scene.version)
        if key == self._key:
            return False
        self._key = key
        self.panels = [p for p in all_panels(scene) if scene.entity_visible(p.group)]
        self.boxes = Boxes(self.panels)
        return True


def _runs(status, wanted, closed):
    """Відрізки зі станом ``wanted`` поспіль: ``[(перший, кількість)]``."""
    n = len(status)
    hit = [bool(v == wanted) for v in status]
    if closed and all(hit):
        return [(0, n)]
    first = hit.index(False) if closed and False in hit else 0
    out, run = [], 0
    for k in range(n + 1):
        i = (first + k) % n if closed else k
        if k < n and hit[i]:
            run += 1
        elif run:
            out.append(((first + k - run) % n if closed else k - run, run))
            run = 0
    return out


class HoleOverlay:
    """Накладка з отворами всіх видимих панелей."""

    FACE = QColor(220, 95, 20)
    SIDE = QColor(40, 110, 220)

    def __init__(self, app):
        self.app = app
        self.visible = True
        self._scene = SceneBoxes()
        self._status_key = None
        self._collect()

    # ---- отвори ----
    def _collect(self):
        """Геометрія отворів у світі (м) — масивами, раз на зміну документа."""
        rows = []
        for p in self._scene.panels:
            L, W, T = p.size
            for h in p.data["holes"]:
                c, n = hole_world(p, h)
                face = h["type"] == "face"
                through = T if face else (W if h.get("side", 0) in (0, 2) else L)
                depth = through if h.get("depth") is None else h["depth"] / 1000
                u = p.R[:, 0] if face else p.R[:, 2]
                rows.append((c, n, u, np.cross(n, u), h["d"] / 2000, depth, face))
        cols = list(zip(*rows)) if rows else [()] * 7
        self.c, self.n, self.u, self.v = (
            np.array(x, dtype=np.float64).reshape(-1, 3) for x in cols[:4])
        self.r = np.array(cols[4], dtype=np.float64)
        self.depth = np.array(cols[5], dtype=np.float64)
        self.face = cols[6]
        self.bottom = self.c - self.n * self.depth[:, None]
        boxes = self._scene.boxes
        self.own = boxes.touch(self.c) | boxes.touch(self.bottom)
        a = np.arange(RING) * (2 * np.pi / RING)
        radial = (np.cos(a)[None, :, None] * self.u[:, None]
                  + np.sin(a)[None, :, None] * self.v[:, None]) * self.r[:, None, None]
        self.mouth_ring = self.c[:, None] + radial
        self.bottom_ring = self.bottom[:, None] + radial
        self._status_key = None

    def _outline(self, view):
        """Точки контурів: два кола (N, RING, 3) і дві твірні, дотичні до
        погляду (N, 2, LINE + 1, 3)."""
        look = view.forward if view.eye is None else self.c - view.eye
        t = np.cross(self.n, look)
        size = np.linalg.norm(t, axis=1, keepdims=True)
        t = np.where(size > 1e-9, t / np.maximum(size, 1e-9), 0.0) * self.r[:, None]
        k = np.linspace(0.0, 1.0, LINE + 1)[None, None, :, None]
        ends = np.stack([t, -t], axis=1)
        a, b = self.c[:, None] + ends, self.bottom[:, None] + ends
        return a[:, :, None] * (1 - k) + b[:, :, None] * k

    def classify(self, view):
        """Стан відрізків: ``(устя, дно, твірні)`` і точки твірних."""
        key = _view_key(view)
        if key != self._status_key:
            lines = self._outline(view)
            parts = [(r + np.roll(r, -1, axis=1)) / 2
                     for r in (self.mouth_ring, self.bottom_ring)]
            mids = (lines[:, :, :-1] + lines[:, :, 1:]) / 2
            parts.append(mids.reshape(len(mids), 2 * LINE, 3))
            st = self._scene.boxes.status(view, np.concatenate(parts, axis=1), self.own)
            self._status = (st[:, :RING], st[:, RING:2 * RING],
                            st[:, 2 * RING:].reshape(-1, 2, LINE), lines)
            self._status_key = key
        return self._status

    # ---- малювання ----
    def __call__(self, viewport, painter):
        if not self.visible or not shown_in(viewport):
            return
        if self._scene.update(viewport.scene):
            self._collect()
        n = len(self.r)
        if not n:
            return
        mouth, bottom, gen, lines = self.classify(view_of(viewport))
        pts = np.concatenate([self.mouth_ring, self.bottom_ring,
                              lines.reshape(n, 2 * (LINE + 1), 3)], axis=1)
        px, py, front = viewport.world_to_pixels(pts.reshape(-1, 3))
        xy = np.stack([px, py], axis=1).reshape(n, -1, 2)
        front = np.asarray(front).reshape(n, -1).all(axis=1)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        # Спершу внутрішні, поверх — видимі.
        seen = (mouth == VISIBLE).any(axis=1)
        shown = front & ((mouth != HIDDEN).any(axis=1) | (bottom != HIDDEN).any(axis=1)
                         | (gen != HIDDEN).any(axis=(1, 2)))
        for i in sorted(np.nonzero(shown)[0], key=lambda i: bool(seen[i])):
            self._paint(painter, xy[i], mouth[i], bottom[i], gen[i],
                        self.FACE if self.face[i] else self.SIDE, bool(seen[i]))

    def _paint(self, painter, xy, mouth, bottom, gen, color, seen):
        ring = xy[:RING]
        span = np.ptp(ring, axis=0).max() / 2
        solid = QPen(color, 1.8)
        faint = QColor(color)
        faint.setAlpha(190)
        dashed = QPen(faint, 1.2)
        dashed.setDashPattern([3.0, 2.5])
        fill = QColor(color)
        fill.setAlpha(90)
        painter.setBrush(Qt.NoBrush)
        if span < SMALL:
            if not seen and not (mouth == INSIDE).any():
                return
            p = QPointF(*(float(v) for v in ring.mean(axis=0)))
            painter.setPen(Qt.NoPen if seen else QPen(faint, 1.0))
            painter.setBrush(color if seen else Qt.NoBrush)
            painter.drawEllipse(p, SMALL if seen else 2.0, SMALL if seen else 2.0)
            return
        if (mouth == VISIBLE).all():
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in ring]))
            painter.setBrush(Qt.NoBrush)
        curves = [(ring, mouth, True), (xy[RING:2 * RING], bottom, True)]
        rest = xy[2 * RING:].reshape(2, LINE + 1, 2)
        curves += [(rest[0], gen[0], False), (rest[1], gen[1], False)]
        for k, (pts, status, closed) in enumerate(curves):
            # Глибина пунктиром — лише коли самого устя не видно.
            kinds = ((INSIDE, dashed), (VISIBLE, solid)) if k == 0 or not seen \
                else ((VISIBLE, solid),)
            for wanted, pen in kinds:
                painter.setPen(pen)
                for start, count in _runs(status, wanted, closed):
                    painter.drawPolyline(QPolygonF(
                        [QPointF(float(pts[j % len(pts)][0]), float(pts[j % len(pts)][1]))
                         for j in range(start, start + count + 1)]))
