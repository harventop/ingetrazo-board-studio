# SPDX-License-Identifier: GPL-3.0-or-later
"""Контур панелі: прямі відрізки, дуги й інші криві — за сіткою пласті.

Модуль не залежить від IngeTrazo: на вхід — точки контуру (мм, проти годинникової
стрілки) з позначками гладкості, на виході — список :class:`Segment`. IngeTrazo
зберігає дугу ламаною, тож коло відновлюємо з вершин: для розкрою дуга
дробиться дрібніше, ніж у моделі.
"""
from __future__ import annotations

import math

TOL = 0.02              # мм: вершина «на» колі чи прямій
MAX_TURN = math.radians(36.0)       # більший злам — кут, а не дуга
CURVE_TURN = math.radians(20.0)     # злам кривої без м'якого ребра
CHORD_TOL = 0.05        # мм: відхилення ламаної від дуги в розкрої


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _turn(a, b, c):
    """Злам у точці b, рад: додатний — ліворуч."""
    u, v = _sub(b, a), _sub(c, b)
    return math.atan2(_cross(u, v), _dot(u, v))


def area(pts):
    return sum(_cross(p, q) for p, q in zip(pts, pts[1:] + pts[:1])) / 2


def _circle(a, b, c):
    """Коло через три точки: (центр, радіус) або ``None``."""
    u, v = _sub(b, a), _sub(c, a)
    d = 2 * _cross(u, v)
    if abs(d) < 1e-9:
        return None
    uu, vv = _dot(u, u), _dot(v, v)
    x, y = (v[1] * uu - u[1] * vv) / d, (u[0] * vv - v[0] * uu) / d
    return (a[0] + x, a[1] + y), math.hypot(x, y)


class Segment:
    """Ділянка контуру: ``line``, ``arc`` або ``curve``.

    ``pts`` — вершини моделі разом з обома кінцями, проти годинникової стрілки по
    контуру. ``side`` — номер сторони 0..3, якщо пряма лежить на габариті."""

    def __init__(self, kind, pts, center=None, radius=0.0, sweep=0.0):
        self.kind, self.pts = kind, pts
        self.center, self.radius, self.sweep = center, radius, sweep
        self.side = None
        self.key = None             # side або ("x", номер ділянки)

    @property
    def length(self):
        return sum(math.dist(p, q) for p, q in zip(self.pts, self.pts[1:]))

    def _at(self, u):
        """Точка дуги, u ∈ [0, 1]."""
        x, y = _sub(self.pts[0], self.center)
        a = math.atan2(y, x) + self.sweep * u
        return (self.center[0] + self.radius * math.cos(a),
                self.center[1] + self.radius * math.sin(a))

    def fine(self, tol=CHORD_TOL):
        """Точки для розкрою: дуга — не грубіше за ``tol``, решта — як є."""
        if self.kind != "arc":
            return list(self.pts)
        step = 2 * math.acos(max(-1.0, 1 - min(tol / self.radius, 2.0)))
        n = max(len(self.pts) - 1, math.ceil(abs(self.sweep) / step - 1e-9))
        return [self.pts[0]] + [self._at(i / n) for i in range(1, n)] + [self.pts[-1]]

    def middle(self):
        """Середина ділянки і напрямок контуру в ній (одиничний)."""
        if self.kind == "arc":
            p = self._at(0.5)
            x, y = _sub(p, self.center)
            s = math.copysign(1.0, self.sweep) / self.radius
            return p, (-y * s, x * s)
        left = self.length / 2
        for p, q in zip(self.pts, self.pts[1:]):
            d = math.dist(p, q)
            if left <= d or q is self.pts[-1]:
                t = (q[0] - p[0]) / d, (q[1] - p[1]) / d
                return (p[0] + t[0] * left, p[1] + t[1] * left), t
            left -= d


def _arc_run(pts, i, smooth, curve):
    """Найдовша дуга, що починається ребром ``i``: (кінець, коло) або ``None``.
    ``pts`` — розімкнений список (перша точка повторена в кінці)."""
    n = len(pts) - 1
    best, sign = None, 0.0
    for j in range(i + 1, n):                   # ребра i..j
        t = _turn(pts[j - 1], pts[j], pts[j + 1])
        same = curve[j] is not None and curve[j] == curve[j - 1]
        if not 1e-6 < abs(t) <= MAX_TURN or t * sign < 0:
            break
        if not smooth[j] and not (same and abs(t) <= CURVE_TURN):
            break
        sign = math.copysign(1.0, t)
        run = pts[i:j + 2]
        k = len(run) - 1
        closed = math.dist(run[0], run[-1]) < 1e-9
        c = _circle(run[0], run[k // 3], run[2 * k // 3]) if closed \
            else _circle(run[0], run[k // 2], run[k])
        # Три точки лежать на колі завжди: коротка дуга — лише за спільною кривою.
        if k < 3 and not same:
            continue
        if c is None or any(abs(math.dist(p, c[0]) - c[1]) > TOL for p in run):
            break
        best = j, c, sign
    return best


def segments(pts, smooth, curve, length, width):
    """Розбити замкнений контур ``pts`` (проти стрілки) на ділянки.

    ``smooth[i]`` — чи вершина i гладка (м'яке вертикальне ребро); ``curve[i]`` —
    номер кривої ребра i → i+1 або ``None``; ``length``, ``width`` — габарит."""
    n = len(pts)
    # Від кінця найдовшого ребра: так жодна дуга не розрізана початком.
    s = (max(range(n), key=lambda i: math.dist(pts[i], pts[(i + 1) % n])) + 1) % n
    pts = pts[s:] + pts[:s + 1]
    smooth, curve = smooth[s:] + smooth[:s], curve[s:] + curve[:s]
    out, i = [], 0
    while i < n:
        run = _arc_run(pts, i, smooth, curve)
        if run is not None:
            j, (c, r), sign = run
            chord = pts[i:j + 2]
            sweep = sign * sum(2 * math.asin(min(1.0, math.dist(p, q) / (2 * r)))
                               for p, q in zip(chord, chord[1:]))
            out.append(Segment("arc", chord, c, r, sweep))
            i = j + 1
            continue
        j = i
        while (curve[i] is not None and j + 1 < n and curve[j + 1] == curve[i]
               and (smooth[j + 1]
                    or abs(_turn(pts[j], pts[j + 1], pts[j + 2])) <= CURVE_TURN)):
            j += 1
        if j > i:
            out.append(Segment("curve", pts[i:j + 2]))
            i = j + 1
            continue
        # Пряма: розрізані ребра на одній лінії — разом.
        while j + 1 < n and _straight(pts[i], pts[j + 1], pts[j + 2]):
            j += 1
        out.append(Segment("line", [pts[i], pts[j + 1]]))
        i = j + 1
    _join_ends(out)
    for k, seg in enumerate(out):
        seg.side = _side(seg, length, width)
        seg.key = ("x", k) if seg.side is None else seg.side
    return out


def _straight(a, b, c):
    u, v = _sub(b, a), _sub(c, a)
    d = math.hypot(*v)
    return d > 0 and abs(_cross(u, v)) / d < TOL / 2 and _dot(u, _sub(c, b)) > 0


def _join_ends(out):
    if len(out) > 2 and out[0].kind == out[-1].kind == "line" \
            and _straight(out[-1].pts[0], out[0].pts[0], out[0].pts[-1]):
        out[0] = Segment("line", [out.pop().pts[0], out[0].pts[-1]])


def _side(seg, length, width):
    if seg.kind != "line":
        return None
    for s, axis, value in ((0, 1, 0.0), (1, 0, length), (2, 1, width), (3, 0, 0.0)):
        if all(abs(p[axis] - value) < 0.1 for p in seg.pts):
            return s
    return None


def is_box(segs):
    """Чи контур — звичайний прямокутник."""
    return len(segs) == 4 and sorted(s.side if s.side is not None else -1
                                     for s in segs) == [0, 1, 2, 3]


# ---- Де в контурі матеріал: ``loops`` — зовнішній контур і вирізи (ламані) ----

def _links(loops):
    for loop in loops:
        yield from zip(loop, loop[1:] + loop[:1])


def inside(loops, p):
    """Чи точка в матеріалі (у вирізі — ні)."""
    odd = False
    for a, b in _links(loops):
        if (a[1] > p[1]) != (b[1] > p[1]) \
                and p[0] < a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
            odd = not odd
    return odd


def spans(loops, p, q):
    """Частини відрізка p → q у матеріалі: ``[(u0, u1)]``, u ∈ [0, 1]."""
    d = _sub(q, p)
    cuts = [0.0, 1.0]
    for a, b in _links(loops):
        e = _sub(b, a)
        den = _cross(d, e)
        if abs(den) < 1e-9:
            continue                    # паралельне ребро не розрізає
        w = _sub(a, p)
        u, v = _cross(w, e) / den, _cross(w, d) / den
        if 0.0 < u < 1.0 and -1e-9 <= v <= 1 + 1e-9:
            cuts.append(u)
    cuts.sort()
    out = []
    for u0, u1 in zip(cuts, cuts[1:]):
        m = (u0 + u1) / 2
        if u1 - u0 < 1e-9 or not inside(loops, (p[0] + d[0] * m, p[1] + d[1] * m)):
            continue
        if out and u0 - out[-1][1] < 1e-9:
            out[-1] = out[-1][0], u1
        else:
            out.append((u0, u1))
    return out


def _to_link(p, a, b):
    d, w = _sub(b, a), _sub(p, a)
    n = _dot(d, d)
    u = min(1.0, max(0.0, _dot(w, d) / n)) if n else 0.0
    return math.dist(p, (a[0] + d[0] * u, a[1] + d[1] * u))


def clear(loops, p, q, r):
    """Чи смуга радіуса ``r`` уздовж p → q уся в матеріалі (отвір, p = q — круглий)."""
    if not inside(loops, p) or (p != q and spans(loops, p, q) != [(0.0, 1.0)]):
        return False
    return all(min(_to_link(p, a, b), _to_link(q, a, b), _to_link(a, p, q), _to_link(b, p, q))
               >= r - TOL for a, b in _links(loops))
