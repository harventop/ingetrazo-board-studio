# SPDX-License-Identifier: GPL-3.0-or-later
"""Експорт деталей у DXF для ViyarPro — формат ``ABF_Flatten``
(див. ``viyar/dfx/FORMAT.md``).

Модуль не залежить від IngeTrazo: на вхід — список :class:`Part` у мм, на
виході — текст DXF R2007. Сенс несуть назви шарів і блоків, тож вони
повторюють зразки ABF дослівно.

Локальна система деталі: X — довжина, Y — ширина, Z — товщина (низ z=0,
верх z=t). Сторони (торці) нумеруються від початку координат проти
годинникової стрілки::

        сторона 2 (y = W)
      +-------------------+
    3 |                   | 1
      +-------------------+
        сторона 0 (y = 0)
"""
from __future__ import annotations

import math
from pathlib import Path
from dataclasses import dataclass, field

#: Атрибут груп отворів під шкант. Назви ABF для окремого шканта у зразках
#: немає (там шкант — частина мініфікса), тож це припущення.
DOWEL_GROUP = "_ABF_dowel"
PANEL_GAP = 100.0       # мм між деталями в розкладці
MATERIAL_GAP = 300.0    # мм між групами матеріалів


@dataclass
class Hole:
    """Отвір у мм, у локальній системі деталі.

    ``kind="face"`` — у пласті: центр ``(x, y)``, ``top`` — на верхній грані
    (z=t), інакше на нижній. ``kind="side"`` — у торці ``side``: центр
    ``(x, y, z)`` лежить на лінії торця (z — висота осі, типово t/2).
    ``depth=None`` — наскрізний."""
    kind: str
    x: float
    y: float
    d: float
    depth: float | None
    top: bool = True
    side: int = 0
    z: float | None = None
    article: str = ""
    group: str = DOWEL_GROUP
    #: Шар явно, якщо він не збігається з діаметром кола (шток мініфікса в
    #: ABF — коло Ø5 на шарі шканта ``D8-DEPTH12-$38878``).
    layer: str = ""


@dataclass
class Edge:
    """Ділянка контуру непрямокутної деталі (локальні мм, обхід проти стрілки):
    точки разом з обома кінцями, середина, напрямок у ній і товщина крайки."""
    pts: list
    middle: tuple
    along: tuple
    band: float = 0.0


@dataclass
class Part:
    name: str
    length: float
    width: float
    thickness: float
    #: Товщина кромки на сторонах 0..3, мм (0 — без кромки).
    edges: tuple = (0.0, 0.0, 0.0, 0.0)
    #: Напрямок текстури: ``"length"``, ``"width"`` або ``"none"``.
    grain: str = "length"
    article: str = ""
    decor: str = ""
    holes: list = field(default_factory=list)
    #: Контур непрямокутної деталі — список :class:`Edge`; порожній — прямокутник
    #: ``length`` × ``width`` з крайкою ``edges``.
    outline: list = field(default_factory=list)


# ---- Назви -----------------------------------------------------------------------

def dxf_name(text):
    """Назва для шару чи блоку: кирилиця та інші символи → ``_`` (як в ABF)."""
    return "".join(ch if ch.isascii() and (ch.isalnum() or ch in ".-_$#") else "_"
                   for ch in str(text))


def num(v):
    """Число без зайвих нулів: 8 → «8», 4.5 → «4.5»."""
    s = f"{float(v):.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def material_block(part):
    t = f"THICKNESS_{num(part.thickness)}"
    article = str(part.article or "").strip().lstrip("$")
    if not article:
        return t
    decor = dxf_name(str(part.decor or "").strip())
    return f"${dxf_name(article)}____{decor}__{t}" if decor else f"${dxf_name(article)}__{t}"


def face_layer(hole):
    if hole.layer:
        return hole.layer
    depth = "F" if hole.depth is None else num(hole.depth)
    article = str(hole.article or "").strip().lstrip("$")
    return f"D{num(hole.d)}-DEPTH{depth}" + (f"-${dxf_name(article)}" if article else "")


def side_layer(hole):
    return f"Dside{num(hole.d)}"


# ---- Розкладка ---------------------------------------------------------------------

def orientation(part):
    """Чи повертати деталь на 90°: текстура в ViyarPro йде вздовж осі Y
    розкладки. Без текстури довша сторона теж лягає вздовж Y (як в ABF)."""
    if part.grain == "length":
        return True
    if part.grain == "width":
        return False
    return part.length >= part.width


def flipped(part):
    """Чи перевертати деталь: верхня грань розкладки для ViyarPro — фронтальна,
    і ABF кладе деталь глухими отворами догори. Наскрізні отвори не рахуємо."""
    top = bottom = 0
    for h in part.holes:
        if h.kind == "face" and h.depth is not None and h.depth < part.thickness:
            top, bottom = top + bool(h.top), bottom + (not h.top)
    return bottom > top


class Placed:
    """Деталь у розкладці: розміри ``a`` (X) × ``b`` (Y) і перетворення
    локальних координат. Переворот — обертання на 180° навколо осі X розкладки,
    тож текстура лишається вздовж Y, а деталь не віддзеркалюється."""

    def __init__(self, part):
        self.part = part
        self.rot = orientation(part)
        self.flip = flipped(part)
        L, W = part.length, part.width
        self.a, self.b = (W, L) if self.rot else (L, W)
        self.t = part.thickness
        self.edges = [0.0] * 4
        for s, e in enumerate(part.edges):
            self.edges[self.side(s)] = float(e or 0.0)

    def point(self, x, y):
        """Локальні (x, y) → (X, Y) розкладки (поворот на +90° навколо Z, переворот)."""
        X, Y = (self.part.width - y, x) if self.rot else (x, y)
        return (X, self.b - Y) if self.flip else (X, Y)

    def outline(self):
        """Контур деталі в розкладці, проти стрілки: від нижнього правого кута
        (найнижча вершина, з них — найправіша)."""
        edges = []
        for e in self.part.outline:
            pts = [self.point(*p) for p in e.pts]
            x0, y0 = self.point(0.0, 0.0)
            x, y = self.point(*e.along)
            along = (x - x0, y - y0)
            if self.flip:
                pts.reverse()
                along = (-along[0], -along[1])
            edges.append(Edge(pts, self.point(*e.middle), along, float(e.band or 0.0)))
        if self.flip:
            edges.reverse()
        return edges

    def side(self, s):
        s = (s + 1) % 4 if self.rot else s
        return (2, 1, 0, 3)[s] if self.flip else s

    def top(self, hole):
        return bool(hole.top) != self.flip

    def height(self, hole):
        """Висота осі торцевого отвору в розкладці."""
        z = self.t / 2 if hole.z is None else hole.z
        return self.t - z if self.flip else z


#: Сторона розкладки → зовнішня нормаль у площині XY.
OUTWARD = ((0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))


# ---- Геометрія блоків --------------------------------------------------------------

def box_faces(a, b, t):
    """Грані бруска: ``[(чотирикутник, [4 ребра])]`` — у порядку ABF.

    Локальний початок — правий нижній кут, деталь лежить на ``x ∈ [-a, 0]``.
    Верх, низ, далі бічні **за годинниковою стрілкою**: низ, ліво, верх, право.
    Порядок перевірено у ViyarPro, не змінювати: з обходом проти стрілки (та іншим
    початком контуру й порядком позначок) не розпізнавались ліва й права крайки."""
    lb, lt, rt, rb = (-a, 0.0), (-a, b), (0.0, b), (0.0, 0.0)

    def up(c):
        return c + (t,)

    def dn(c):
        return c + (0.0,)
    faces = [
        ([up(rb), up(rt), up(lt), up(lb)],
         [(up(rb), up(lb)), (up(rt), up(rb)), (up(lt), up(rt)), (up(lb), up(lt))]),
        ([dn(rt), dn(rb), dn(lb), dn(lt)],
         [(dn(rb), dn(lb)), (dn(lb), dn(lt)), (dn(lt), dn(rt)), (dn(rt), dn(rb))]),
    ]
    quads = ([up(rb), up(lb), dn(lb), dn(rb)], [up(lt), dn(lt), dn(lb), up(lb)],
             [up(lt), up(rt), dn(rt), dn(lt)], [dn(rt), up(rt), up(rb), dn(rb)])
    for quad, (c, d) in zip(quads, ((rb, lb), (lb, lt), (lt, rt), (rt, rb))):
        faces.append((quad, [(up(c), up(d)), (up(d), dn(d)), (dn(c), dn(d)), (up(c), dn(c))]))
    return faces


def cut_contour(a, b, edges):
    """Контур різу проти годинникової стрілки. В ABF він починається з першого
    кута верхньої грані, а на деталі без крайки — з наступного за стрілкою."""
    e0, e1, e2, e3 = edges
    pts = [(-e1, e0, 0.0), (-e1, b - e2, 0.0), (e3 - a, b - e2, 0.0), (e3 - a, e0, 0.0)]
    return pts if any(e > 0 for e in edges) else pts[3:] + pts[:3]


def outline_loop(edges):
    """``(точки, товщини крайки)`` контуру; ``k``-те ребро — від точки k до k+1.
    Починається з найнижчої, з них — найправішої вершини."""
    pts, bands = [], []
    for e in edges:
        pts += e.pts[:-1]
        bands += [e.band] * (len(e.pts) - 1)
    k = min(range(len(pts)), key=lambda i: (round(pts[i][1], 3), -round(pts[i][0], 3)))
    return pts[k:] + pts[:k], bands[k:] + bands[:k]


def outline_faces(pts, t):
    """Грані деталі з контуром ``pts``: як :func:`box_faces` — верх, низ, далі
    бічні за годинниковою стрілкою від першої точки."""
    def up(c):
        return tuple(c) + (t,)

    def dn(c):
        return tuple(c) + (0.0,)
    back = [pts[0]] + pts[:0:-1]                # за стрілкою
    pairs = list(zip(back, back[1:] + back[:1]))
    faces = [([up(c) for c in pts], [(up(c), up(d)) for c, d in pairs]),
             ([dn(c) for c in back], [(dn(c), dn(d)) for c, d in pairs])]
    for c, d in pairs:
        faces.append(([up(c), up(d), dn(d), dn(c)],
                      [(up(c), up(d)), (up(d), dn(d)), (dn(c), dn(d)), (up(c), dn(c))]))
    return faces


def inset(pts, bands):
    """Контур проти стрілки, зсунутий усередину: кожне ребро — на свою крайку."""
    n, out = len(pts), []
    for i, p in enumerate(pts):
        e1, e2 = bands[i - 1], bands[i]
        d1 = _unit2(p, pts[i - 1])
        d2 = _unit2(pts[(i + 1) % n], p)
        n1, n2 = (-d1[1], d1[0]), (-d2[1], d2[0])
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        cross = n1[0] * n2[1] - n1[1] * n2[0]
        if abs(e1 - e2) < 1e-9 and dot > -0.9:
            k = e1 / (1 + dot)
            out.append((p[0] + (n1[0] + n2[0]) * k, p[1] + (n1[1] + n2[1]) * k))
        elif abs(cross) > 0.5:
            out.append((p[0] + (e1 * n2[1] - e2 * n1[1]) / cross,
                        p[1] + (e2 * n1[0] - e1 * n2[0]) / cross))
        else:                                   # майже пряма, крайка різна — сходинка
            out += [(p[0] + n1[0] * e1, p[1] + n1[1] * e1),
                    (p[0] + n2[0] * e2, p[1] + n2[1] * e2)]
    return out


def _unit2(b, a):
    x, y = b[0] - a[0], b[1] - a[1]
    d = math.hypot(x, y)
    return x / d, y / d


def outline_marks(edges, a, b):
    """Трикутники-позначки крайки для ділянок контуру: вершина — біля середини
    ділянки, дивиться назовні (для прямих сторін — як :func:`edge_marks`)."""
    h, gap = mark_size(a, b)
    out = []
    for e in edges:
        if e.band <= 0:
            continue
        (tx, ty), (mx, my) = e.along, e.middle
        nx, ny = -ty, tx                        # всередину
        x, y = mx + nx * (gap + e.band), my + ny * (gap + e.band)
        out.append([(x, y), (x + (nx - tx) * h, y + (ny - ty) * h),
                    (x + (nx + tx) * h, y + (ny + ty) * h)])
    return out


def mark_order(e):
    """Порядок позначок як в ABF: низ, ліво, право, верх; похилі — до найближчої."""
    nx, ny = e.along[1], -e.along[0]            # назовні
    k = max(range(4), key=lambda s: round(nx * OUTWARD[s][0] + ny * OUTWARD[s][1], 6))
    return (0, 3, 1, 2).index(k)


def panel_entities(p, blocks, counter):
    """Вміст блоку деталі: брусок, отвори, контур різу, позначки кромки.
    Початок координат блоку — правий нижній кут деталі (див. box_faces)."""
    a, b, t = p.a, p.b, p.t
    shape = sorted(p.outline(), key=mark_order) if p.part.outline else []
    if shape:
        loop, bands = outline_loop([Edge([(x - a, y) for x, y in e.pts], e.middle, e.along, e.band)
                                    for e in p.outline()])
        banded = any(e > 0 for e in bands)
        faces = outline_faces(loop, t)
    else:
        banded = any(e > 0 for e in p.edges)
        faces = box_faces(a, b, t)
    line_layer = "0" if banded else "ABF_cuttingLines"
    ents = []
    for k, (quad, lines) in enumerate(faces):
        ents.append(("POLYFACE", "0", 7 if k == 0 else 0, quad))
        ents += [("LINE", line_layer, 0, p1, p2) for p1, p2 in lines]

    for h in p.part.holes:
        X, Y = p.point(h.x, h.y)
        X -= a
        if h.kind == "face":
            z, n = (t, (0.0, 0.0, 1.0)) if p.top(h) else (0.0, (0.0, 0.0, -1.0))
            at = (X, Y, z)
            name = f"Group{next(counter)}#1"
            blocks[name] = [("CIRCLE", face_layer(h), 0, (0.0, 0.0, 0.0), h.d / 2, n)]
            ents.append(("INSERT", "0", name, at, h.group))
        else:
            s = p.side(h.side)
            ox, oy = OUTWARD[s]
            zc = p.height(h)
            layer = side_layer(h)
            name = f"Group{next(counter)}#1"
            blocks[name] = [("CIRCLE", layer, 0, (0.0, 0.0, zc - t), h.d / 2, (ox, oy, 0.0))]
            ents.append(("INSERT", "0", name, (X, Y, t), "_ABF_sideDrill"))
            depth = (a if s in (1, 3) else b) if h.depth is None else h.depth
            r = h.d / 2
            ix, iy = -ox, -oy                   # всередину деталі
            px, py = -iy, ix                    # уздовж торця
            quad = [(px * r, py * r, 0.0), (px * r + ix * depth, py * r + iy * depth, 0.0),
                    (-px * r + ix * depth, -py * r + iy * depth, 0.0), (-px * r, -py * r, 0.0)]
            name = f"Group{next(counter)}#1"
            blocks[name] = [("POLY", layer, 0, quad)]
            ents.append(("INSERT", "0", name, (X, Y, t), "_ABF_sideDrillDepth"))

    name = f"Group{next(counter)}#1"
    if shape:
        contour = [(x, y, 0.0) for x, y in inset(loop, bands)]
        if not banded:                          # як cut_contour
            contour = contour[-1:] + contour[:-1]
    else:
        contour = cut_contour(a, b, p.edges)
    blocks[name] = [("POLY", "ABF_cuttingLines", 0, contour)]
    ents.append(("INSERT", "ABF_cuttingLines", name, (0.0, 0.0, t), "_ABF_cuttingLines"))

    if banded:
        name = f"Group{next(counter)}#1"
        if shape:
            tips = outline_marks(shape, a, b)
        else:
            marks = edge_marks(a, b, p.edges)
            tips = [marks[s] for s in (0, 3, 1, 2) if p.edges[s] > 0]
        blocks[name] = [("POLY", "ABF_edgeBanding", 0, [(x - a, y) for x, y in mark])
                        for mark in tips]
        ents.append(("INSERT", "ABF_edgeBanding", name, (0.0, 0.0, t), "_ABF_edgeBanding"))
    # Мітку напрямку текстури ABF (трикутник + ромб, шар ABF_Label) не
    # малюємо: напрямок задає орієнтація деталі в розкладці (текстура — по Y).
    return ents


#: Розмір позначки кромки у зразках ABF: менша сторона деталі → (висота
#: трикутника, у скільки разів відступ вершини від лінії різу менший за висоту).
#: Формула ABF невідома, тож між зразками — лінійна інтерполяція.
MARK_SAMPLES = ((200.0, 17.9780582753, 7.0), (300.0, 25.9183673469, 6.0),
                (500.0, 35.3985824640, 5.0))


def mark_size(a, b):
    """``(висота, відступ)`` трикутника кромки для деталі ``a`` × ``b``."""
    m = min(a, b)
    if m <= MARK_SAMPLES[0][0]:
        m0, h0, k = MARK_SAMPLES[0]
        ratio = h0 / m0
    elif m >= MARK_SAMPLES[-1][0]:
        m0, h0, k = MARK_SAMPLES[-1]
        ratio = h0 / m0
    else:
        for (m0, h0, k0), (m1, h1, k1) in zip(MARK_SAMPLES, MARK_SAMPLES[1:]):
            if m <= m1:
                u = (m - m0) / (m1 - m0)
                ratio = h0 / m0 + u * (h1 / m1 - h0 / m0)
                k = k0 + u * (k1 - k0)
                break
    h = ratio * m
    return h, h / k


def edge_marks(a, b, edges=(0.0, 0.0, 0.0, 0.0)):
    """Трикутники-позначки кромки для сторін 0..3; вершина дивиться на сторону.
    Відступ вершини відлічується від лінії різу, а не від краю деталі."""
    h, gap = mark_size(a, b)
    e0, e1, e2, e3 = (gap + e for e in edges)
    cx, cy = a / 2, b / 2
    return [
        [(cx, e0), (cx - h, e0 + h), (cx + h, e0 + h)],
        [(a - e1, cy), (a - e1 - h, cy - h), (a - e1 - h, cy + h)],
        [(cx, b - e2), (cx + h, b - e2 - h), (cx - h, b - e2 - h)],
        [(e3, cy), (e3 + h, cy + h), (e3 + h, cy - h)],
    ]


def layout(parts):
    """``[(material block, [(Placed, x0)])]`` — деталі в ряд уздовж −X."""
    groups = {}
    for part in parts:
        groups.setdefault(material_block(part), []).append(Placed(part))
    out, cursor = [], 0.0
    for gi, (mat, placed) in enumerate(groups.items()):
        if gi:
            cursor -= MATERIAL_GAP - PANEL_GAP
        row = []
        for p in placed:
            x0 = cursor - p.a
            row.append((p, x0))
            cursor = x0 - PANEL_GAP
        out.append((mat, row))
    return out


# ---- Збирання документа ----------------------------------------------------------------

def build(parts):
    """``(blocks, model_space)``: блоки ``{name: [entity]}`` і сутності моделі."""
    counter = iter(range(1, 1_000_000))
    # Порядок блоків як в ABF: матеріали, вкладені групи, деталі, підписи.
    mats, leaves, panels = {}, {}, {}
    model = []
    dims = []
    for mat, row in layout(parts):
        items = []
        for p, x0 in row:
            name = f"Group{next(counter)}#1"
            panels[name] = panel_entities(p, leaves, counter)
            items.append(("INSERT", "0", name, (x0 + p.a, 0.0, 0.0), dxf_name(p.part.name) or "__"))
        mats[mat] = items
        model.append(("INSERT", "0", mat, (0.0, 0.0, 0.0), "ABF_Flatten", "Skp_ComponentInstanceName"))
        xs = [x0 for _p, x0 in row] + [x0 + p.a for p, x0 in row]
        dims.append((mat, min(xs), max(xs)))
    labels = f"Group{next(counter)}#1"
    blocks = {**mats, **leaves, **panels}
    blocks[labels] = [("DIMENSION", mat, x0, x1) for mat, x0, x1 in dims]
    model.append(("INSERT", "0", labels, (0.0, 0.0, 0.0), "ABF_Flatten"))
    return blocks, model


def export(parts, path):
    with open(path, "w", encoding="ascii", errors="replace", newline="\r\n") as fh:
        fh.write(to_dxf(parts))


def to_dxf(parts):
    blocks, model = build(parts)
    return _Writer(blocks, model).text()


# ---- Запис DXF R2007 ---------------------------------------------------------------
#
# Службові секції (HEADER, CLASSES, таблиці, OBJECTS) беремо дослівно з файлу
# ABF — ``abf_template.dxf`` (його робить ``scripts/make_dxf_template.py``).
# ViyarPro читає DXF суворіше за звичайні переглядачі: з мінімальним
# «власним» скелетом файл не імпортувався («тільки 2D»). Ще одна прикмета
# деталі в ABF — матеріал ``ABF_Top_Faces`` на верхній грані бруска; решта
# сутностей посилається на ``ByBlock``.

TEMPLATE = Path(__file__).with_name("abf_template.dxf")

def ocs_axes(n):
    """Arbitrary axis algorithm (DXF): осі OCS для нормалі ``n``."""
    n = _unit(n)
    if abs(n[0]) < 1 / 64 and abs(n[1]) < 1 / 64:
        ax = _cross((0.0, 1.0, 0.0), n)
    else:
        ax = _cross((0.0, 0.0, 1.0), n)
    ax = _unit(ax)
    return ax, _unit(_cross(n, ax)), n


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _normal(q):
    """Нормаль грані (не одинична); багатокутника — за Ньюеллом."""
    if len(q) == 4:
        return _cross(tuple(b - a for a, b in zip(q[0], q[1])),
                      tuple(b - a for a, b in zip(q[0], q[2])))
    total = (0.0, 0.0, 0.0)
    for a, b in zip(q, q[1:] + q[:1]):
        total = tuple(s + c for s, c in zip(total, _cross(a, b)))
    return total


def triangulate(pts):
    """Простий багатокутник (2D, обхід проти стрілки) → трійки індексів."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    left, out = list(range(len(pts))), []
    while len(left) > 3:
        best = None
        # «Вухо» може зачепити лише увігнута вершина — в опуклій деталі їх немає.
        reflex = [j for i, j, m in zip(left[-1:] + left, left, left[1:] + left[:1])
                  if cross(pts[i], pts[j], pts[m]) <= 1e-9]
        for k in range(len(left)):
            i, j, m = left[k - 1], left[k], left[(k + 1) % len(left)]
            A, B, C = pts[i], pts[j], pts[m]
            size = cross(A, B, C)
            if size <= 1e-9:
                continue
            if any(cross(A, B, pts[q]) >= 0 and cross(B, C, pts[q]) >= 0
                   and cross(C, A, pts[q]) >= 0 for q in reflex if q not in (i, j, m)):
                continue
            # З можливих «вух» — найменш гостре: без довгих тонких трикутників.
            longest = max(math.dist(A, B), math.dist(B, C), math.dist(C, A))
            if best is None or size / longest ** 2 > best[0]:
                best = size / longest ** 2, k, (i, j, m)
        if best is None:                        # вироджений залишок
            best = 0.0, 1, (left[0], left[1], left[2])
        out.append(best[2])
        del left[best[1]]
    return out + [tuple(left)]


def polyface(q):
    """``(вершини, грані)`` polyface: невидимі діагоналі — з мінусом."""
    if len(q) == 4:
        # 1–2 — діагональ (порядок ABF).
        return (q[0], q[2], q[3], q[1]), ((-1, 2, 3), (-2, 1, 4))
    n = len(q)
    flat = [(p[0], p[1]) for p in q]
    down = _normal(q)[2] < 0
    tris = triangulate([(x, -y) for x, y in flat] if down else flat)
    return q, [tuple(i + 1 if j == (i + 1) % n else -(i + 1)
                     for i, j in zip(t, t[1:] + t[:1])) for t in tris]


def _unit(a):
    n = math.sqrt(sum(x * x for x in a))
    return tuple(x / n for x in a)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _f(v):
    v = round(float(v), 10)
    return "0.0" if v == 0 else repr(v)


class _Template:
    """Шаблон як список записів ``[(code, value)]`` по секціях."""

    def __init__(self, path=TEMPLATE):
        lines = Path(path).read_text(encoding="ascii").splitlines()
        self.pairs = [(int(lines[i]), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
        handles = [int(v, 16) for c, v in self.pairs if c in (5, 105)]
        self.max_handle = max(handles)
        self.materials = {}
        self.layer_defaults = {}
        self.dim_height = 40.0
        rec = []
        self._records = []
        for code, value in self.pairs + [(0, "EOF")]:
            if code == 0 and rec:
                self._records.append(rec)
                d = dict(rec)
                if rec[0][1] == "MATERIAL":
                    self.materials[d.get(1)] = d[5]
                if rec[0][1] == "DIMSTYLE" and d.get(2) == DIM_STYLE:
                    self.dim_height = float(d.get(140, self.dim_height))
                if rec[0][1] == "LAYER" and d.get(2) == "0":
                    self.layer_defaults = {"390": d.get(390), "347": d.get(347)}
                if rec[0][1] == "TABLE":
                    setattr(self, "table_" + d[2], d[5])
                rec = []
            rec.append((code, value))

    def records(self, kind):
        return [r for r in self._records if r[0][1] == kind]


def material_mapper(q):
    """Xdata ``ACAD_MATERIAL_MAPPER`` грані: осі як у SketchUp — для бічних
    граней X = Z×n, Y = Z. Останній вектор — нормаль із додатним знаком."""
    n = _unit(_normal(q))
    if abs(n[2]) > 0.5:
        ax, ay = (math.copysign(1.0, n[2]), 0.0, 0.0), (0.0, 1.0, 0.0)
    else:
        ax, ay = _unit(_cross((0.0, 0.0, 1.0), n)), (0.0, 0.0, 1.0)
    out = [(1001, "ACAD_MATERIAL_MAPPER"), (1070, 1), (1070, 1), (1070, 1)]
    for v in ((0.0, 0.0, 0.0), tuple(25.4 * c for c in ax), tuple(25.4 * c for c in ay),
              tuple(abs(c) for c in n)):
        out += [(1011, _f(v[0])), (1021, _f(v[1])), (1031, _f(v[2]))]
    return out


#: Розмірний стиль підписів і кольори шарів (ACI, true color) — як у зразках ABF.
DIM_STYLE = "DimStyle1"
DIM_Y, DIM_EXT = -200.0, 200.0 / 11
LAYER_COLORS = ((36, 6702080), (134, 39303), (7, 16777215), (190, 10027263))


def _int_width(code):
    """Ширина цілого поля: SketchUp вирівнює їх пробілами."""
    if 60 <= code <= 79 or 170 <= code <= 179 or 270 <= code <= 299 \
            or 370 <= code <= 389 or code == 1070:
        return 6
    return 9 if 90 <= code <= 99 or 420 <= code <= 429 else 0


class _Writer:
    def __init__(self, blocks, model, template=None):
        self.blocks, self.model = blocks, model
        self.tpl = template or _Template()
        self._h = self.tpl.max_handle
        self.out = []
        self.by_block = self.tpl.materials.get("ByBlock")
        self.top_faces = self.tpl.materials.get("ABF_Top_Faces")
        self.dim_blocks = {}
        layers = set()
        for items in list(blocks.values()) + [model]:
            for e in items or ():
                layers.add(e[1] if e[0] != "DIMENSION" else "0")
        # Спершу шари отворів, потім ABF_* — порядок зразків з фурнітурою.
        self.layers = sorted(layers - {"0", "Defpoints"}, key=lambda n: (n.startswith("ABF_"), n))
        self.refs = {}          # блок → ручки INSERT, що на нього посилаються
        self.dim_handles = []
        n = 0
        for items in blocks.values():
            for e in items:
                if e[0] == "DIMENSION":
                    n += 1
                    self.dim_blocks[id(e)] = f"*D{n}"
        self.rec = {}

    def h(self):
        self._h += 1
        return f"{self._h:X}"

    def tag(self, code, value):
        if width := _int_width(code):
            value = f"{value:>{width}}"
        self.out.append(f"{code:>3}\n{value}\n")

    def tags(self, *pairs):
        for code, value in pairs:
            self.tag(code, value)

    def point(self, p, base=10):
        self.tags((base, _f(p[0])), (base + 10, _f(p[1])), (base + 20, _f(p[2] if len(p) > 2 else 0.0)))

    # -- документ --
    def text(self):
        names = list(self.blocks) + list(self.dim_blocks.values())
        self.layer_h = {name: self.h() for name in self.layers}
        self.rec = {name: self.h() for name in names}
        self.ms_rec = next(dict(r)[5] for r in self.tpl.records("BLOCK_RECORD")
                           if dict(r).get(2) == "*Model_Space")
        # Тіло — наперед: таблиці посилаються на ручки INSERT і DIMENSION.
        blocks_text, entities_text = self._blocks(), self._entities()
        out, section, kind, table = [], None, None, None
        pairs = self.tpl.pairs
        i = 0
        while i < len(pairs):
            code, value = pairs[i]
            if code == 0:
                kind = value
                if value == "SECTION":
                    section = pairs[i + 1][1]
                elif value == "TABLE":
                    table = pairs[i + 1][1]
                elif value == "LAYER" and self._record_name(i) == "Defpoints":
                    out.append(self._flush(self._layers))       # Defpoints — останній
                elif value == "ENDTAB" and table == "BLOCK_RECORD":
                    out.append(self._flush(self._block_records))
                elif value == "ENDSEC" and section == "BLOCKS":
                    out.append(blocks_text)
                elif value == "ENDSEC" and section == "ENTITIES":
                    out.append(entities_text)
            if section == "HEADER" and code == 9 and value == "$HANDSEED":
                out.append(f"{code:>3}\n{value}\n")
                i += 2                       # значення — нижче, коли знатимемо всі ручки
                out.append(None)
                continue
            if kind == "TABLE" and code == 70 and table in ("LAYER", "BLOCK_RECORD"):
                # Кількість записів; BLOCK_RECORD — без *Model_Space і *Paper_Space.
                own = len(self.layers) if table == "LAYER" else len(self.rec) - 2
                value = f"{len(self.tpl.records(table)) + own:>6}"
            out.append(f"{code:>3}\n{value}\n")
            if kind == "DIMSTYLE" and code == 105 and self.dim_handles \
                    and self._record_name(i) == DIM_STYLE:
                out.append(self._flush(self.tags, (102, "{ACAD_REACTORS"),
                                       *((330, h) for h in self.dim_handles), (102, "}")))
            i += 1
        seed = f"  5\n{self._h + 1:X}\n"
        return "".join(seed if part is None else part for part in out) + "  0\nEOF\n"

    def _flush(self, fn, *args):
        saved, self.out = self.out, []
        fn(*args)
        text, self.out = "".join(self.out), saved
        return text

    def _record_name(self, i):
        """Назва (код 2) запису таблиці, якому належить пара ``i``."""
        for code, value in self.tpl.pairs[i + 1:]:
            if code == 2:
                return value
            if code == 0:
                return None

    def _layers(self):
        d = self.tpl.layer_defaults
        for i, name in enumerate(self.layers):
            aci, rgb = LAYER_COLORS[i % len(LAYER_COLORS)]
            self.tags((0, "LAYER"), (5, self.layer_h[name]), (330, self.tpl.table_LAYER),
                      (100, "AcDbSymbolTableRecord"), (100, "AcDbLayerTableRecord"), (2, name),
                      (70, 0), (62, aci), (420, rgb), (6, "Continuous"), (370, -3))
            if d.get("390"):
                self.tag(390, d["390"])
            if d.get("347"):
                self.tag(347, d["347"])

    def _block_records(self):
        for name, handle in self.rec.items():
            self.tags((0, "BLOCK_RECORD"), (5, handle), (330, self.tpl.table_BLOCK_RECORD),
                      (100, "AcDbSymbolTableRecord"), (100, "AcDbBlockTableRecord"), (2, name),
                      (340, "0"))
            if self.refs.get(name):
                self.tags((102, "{BLKREFS"), *((331, h) for h in self.refs[name]), (102, "}"))
            self.tags((70, 0), (280, 1), (281, 0))

    def _blocks(self):
        def write():
            for name, items in self.blocks.items():
                self._block(name, items, 0)
            for items in self.blocks.values():
                for e in items:
                    if e[0] == "DIMENSION":
                        self._block(self.dim_blocks[id(e)], self._dim_geometry(e), 1)
        return self._flush(write)

    def _block(self, name, items, flags):
        owner = self.rec[name]
        self.tags((0, "BLOCK"), (5, self.h()), (330, owner), (100, "AcDbEntity"),
                  (8, "0"), (100, "AcDbBlockBegin"), (2, name), (70, flags))
        self.point((0, 0, 0))
        self.tags((3, name), (1, ""))
        for e in items:
            self._entity(e, owner)
        self.tags((0, "ENDBLK"), (5, self.h()), (330, owner), (100, "AcDbEntity"),
                  (8, "0"), (100, "AcDbBlockEnd"))

    def _entities(self):
        def write():
            for e in self.model:
                self._entity(e, self.ms_rec)
        return self._flush(write)

    def _common(self, kind, owner, layer, color=None, material=None, true_color=False):
        h = self.h()
        self.tags((0, kind), (5, h), (330, owner), (100, "AcDbEntity"), (8, layer))
        if material:
            self.tag(347, material)
        if color is not None:
            self.tag(62, color)
        if true_color:
            self.tag(420, 16777215)
        return h

    def _entity(self, e, owner):
        kind = e[0]
        bb = self.by_block
        if kind == "LINE":
            _k, layer, color, p1, p2 = e
            self._common("LINE", owner, layer, color, bb)
            self.tag(100, "AcDbLine")
            self.point(p1)
            self.point(p2, 11)
        elif kind == "CIRCLE":
            _k, layer, color, c, r, n = e
            ax, ay, az = ocs_axes(n)
            self._common("CIRCLE", owner, layer, color)
            self.tag(100, "AcDbCircle")
            self.point((_dot(c, ax), _dot(c, ay), _dot(c, az)))
            self.tag(40, _f(r))
            self.point(az, 210)
        elif kind == "POLY":
            _k, layer, color, pts = e
            pts = [tuple(p) + (0.0,) * (3 - len(p)) for p in pts]
            h = self._common("POLYLINE", owner, layer, color, bb)
            self.tags((100, "AcDb3dPolyline"), (66, 1))
            self.point((0, 0, 0))
            self.tag(70, 9)
            for p in pts + pts[:1]:
                self._common("VERTEX", h, layer, color)
                self.tags((100, "AcDbVertex"), (100, "AcDb3dPolylineVertex"))
                self.point(p)
                self.tag(70, 32)
            self._common("SEQEND", h, layer, color, bb)
        elif kind == "POLYFACE":
            _k, layer, color, q = e
            top = color == 7
            mat = self.top_faces if top else bb
            h = self._common("POLYLINE", owner, layer, color, mat, top)
            self.tags((100, "AcDbPolyFaceMesh"), (66, 1))
            self.point((0, 0, 0))
            verts, tris = polyface(q)
            self.tags((70, 64), (71, len(verts)), (72, len(tris)), *material_mapper(q))
            for p in verts:
                self._common("VERTEX", h, layer, color, None, top)
                self.tags((100, "AcDbVertex"), (100, "AcDbPolyFaceMeshVertex"))
                self.point(p)
                self.tag(70, 192)
            for f in tris:
                self._common("VERTEX", h, layer, color, None, top)
                self.tag(100, "AcDbFaceRecord")
                self.point((0, 0, 0))
                self.tags((70, 128), (71, f[0]), (72, f[1]), (73, f[2]))
            self._common("SEQEND", h, layer, color, mat, top)
        elif kind == "INSERT":
            _k, layer, block, at, value, *rest = e
            tag = rest[0] if rest else "Skp_GroupInstanceName"
            h = self._common("INSERT", owner, layer, 0, bb)
            self.tags((100, "AcDbBlockReference"), (66, 1), (2, block))
            self.point(at)
            self.refs.setdefault(block, []).append(h)
            self._common("ATTRIB", h, "0")
            self.tag(100, "AcDbText")
            self.point((0, 0, 0))
            self.tags((40, "0.2" if tag == "Skp_ComponentInstanceName" else "1.0"), (1, value), (100, "AcDbAttribute"), (2, tag), (70, 0), (280, 0))
            self._common("SEQEND", h, layer, 0, bb)
        elif kind == "DIMENSION":
            _k, text, x0, x1 = e
            h = self._common("DIMENSION", owner, "0", 250)
            self.dim_handles.append(h)
            self.tags((420, 4144959), (100, "AcDbDimension"), (2, self.dim_blocks[id(e)]))
            self.point((x0, DIM_Y, 0))
            self.point(((x0 + x1) / 2, DIM_Y - self.tpl.dim_height, 0), 11)
            self.tags((70, 32), (1, text), (71, 5), (42, _f(x1 - x0)), (73, 0), (74, 0), (75, 0),
                      (3, DIM_STYLE), (100, "AcDbAlignedDimension"))
            self.point((x1, DIM_Y + DIM_EXT, 0), 13)
            self.point((x0, DIM_Y + DIM_EXT, 0), 14)
            self.tags((100, "AcDbRotatedDimension"), (1001, "ACAD"), (1000, "DSTYLE"),
                      (1002, "{"), (1070, 73), (1070, 0), (1002, "}"))
        elif kind == "DIMLINE":
            _k, p1, p2 = e
            self._common("LINE", owner, "0", 0)
            self.tags((370, -2), (100, "AcDbLine"))
            self.point(p1)
            self.point(p2, 11)
        elif kind == "SOLID":
            _k, pts = e
            self._common("SOLID", owner, "0", 0)
            self.tag(100, "AcDbTrace")
            for i, p in enumerate(pts):
                self.point(p, 10 + i)
        elif kind == "MTEXT":
            _k, layer, at, height, text = e
            self._common("MTEXT", owner, layer, 0)
            self.tag(100, "AcDbMText")
            self.point(at)
            self.tags((40, _f(height)), (41, "0.0"), (46, "0.0"), (71, 5), (72, 1), (1, text),
                      (7, "Tahoma"), (73, 1), (44, "1.0"))
        elif kind == "POINT":
            _k, layer, p = e
            self._common("POINT", owner, layer, 0)
            self.tag(100, "AcDbPoint")
            self.point(p)
        else:                                   # pragma: no cover
            raise ValueError(kind)

    def _dim_geometry(self, e):
        _k, text, x0, x1 = e
        y, a, w = DIM_Y, 12.7, 12.7 / 6             # стрілка: довжина, пів ширини
        return [("DIMLINE", (x1, y + 5.481818, 0), (x1, y - a, 0)),
                ("DIMLINE", (x0, y + 5.481818, 0), (x0, y - a, 0)),
                ("DIMLINE", (x1 - a, y, 0), (x0 + a, y, 0)),
                ("SOLID", ((x1 - a, y - w), (x1 - a, y + w), (x1, y), (x1, y))),
                ("SOLID", ((x0 + a, y + w), (x0 + a, y - w), (x0, y), (x0, y))),
                ("MTEXT", "0", ((x0 + x1) / 2, y - self.tpl.dim_height, 0), self.tpl.dim_height,
                 "\\A1;" + text),
                ("POINT", "Defpoints", (x1, y + DIM_EXT, 0)),
                ("POINT", "Defpoints", (x0, y + DIM_EXT, 0)),
                ("POINT", "Defpoints", (x0, y, 0))]
