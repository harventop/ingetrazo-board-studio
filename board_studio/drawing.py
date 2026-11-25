# SPDX-License-Identifier: GPL-3.0-or-later
"""Креслення кріплення для вікна налаштувань (QPainter).

- :class:`JointDrawing` — дві панелі стику у двох узгоджених видах: переріз
  стику і вид на пласть A. На кожному отворі — номер рядка таблиці, діаметр і
  глибина; зсув уздовж стику й відстань від торця — розмірними лініями.
- :class:`PlacementDrawing` — точки кріплення вздовж стику заданої довжини.

Геометрія та сама, що в :mod:`.fasteners`: панель A впирається торцем у
пласть панелі B, отвори торця — по осі товщини A, «внутрішній» бік A — той,
куди від неї тягнеться B (на перерізі — вгору). Клік по отвору або розміру
випускає :attr:`picked`; активний рядок і поле підсвічуються.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import fasteners

# Папір світлий незалежно від теми програми — це креслення.
PAPER, INK, MUTED = QColor("#ffffff"), QColor("#1c2430"), QColor("#7a8594")
A_FILL, A_INK = QColor("#e6effb"), QColor("#2f66b0")
B_FILL, B_INK = QColor("#fbf0dc"), QColor("#c2552d")
ACTIVE = QColor("#d81b60")
ROW = 17.0              # висота рядка підпису, px
A_HOLES = ("edge", "inner_face")


def num(v):
    return f"{round(float(v), 1):g}"


def _alpha(color, a):
    c = QColor(color)
    c.setAlpha(a)
    return c


class _Drawing(QWidget):
    #: (рядок таблиці або -1, ключ поля)
    picked = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hits = []                  # [(QRectF, рядок, ключ)], верхні — в кінці
        self.active = (-1, "")
        self.setMouseTracking(True)

    def set_active(self, row, key):
        if self.active != (row, key):
            self.active = (row, key)
            self.update()

    def hit(self, pos):
        for rect, row, key in reversed(self.hits):
            if rect.contains(pos):
                return row, key
        return None

    def mousePressEvent(self, event):
        target = self.hit(event.position())
        if target is not None and event.button() == Qt.LeftButton:
            self.picked.emit(*target)

    def mouseMoveEvent(self, event):
        self.setCursor(Qt.PointingHandCursor if self.hit(event.position())
                       else Qt.ArrowCursor)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), PAPER)
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        self.hits = []
        self.draw(p)
        p.end()

    # ---- примітиви ----
    def _is_active(self, row, key):
        return self.active == (row, key)

    def _text(self, p, x, y, text, color=INK, bold=False, align="l", hit=None):
        """Рядок тексту, ``y`` — його середина. Повертає зайнятий прямокутник."""
        font = QFont(p.font())
        font.setBold(bold)
        p.save()
        p.setFont(font)
        fm = QFontMetricsF(font)
        w = fm.horizontalAdvance(text)
        x -= {"l": 0.0, "c": w / 2, "r": w}[align]
        rect = QRectF(x, y - ROW / 2, w, ROW)
        if hit is not None:
            self.hits.append((rect.adjusted(-2, 0, 2, 0), *hit))
            if self._is_active(*hit):
                p.fillRect(rect.adjusted(-2, 1, 2, -1), _alpha(ACTIVE, 40))
                color = ACTIVE
        p.setPen(color)
        p.drawText(QPointF(x, y + (fm.ascent() - fm.descent()) / 2), text)
        p.restore()
        return rect

    def _title(self, p, y, text):
        font = QFont(p.font())
        font.setPixelSize(11)
        p.save()
        p.setFont(font)
        self._text(p, 10, y, text.upper(), INK, bold=True)
        p.restore()

    def _arrow(self, p, tip, dx, dy, color):
        """Стрілка з вістрям у ``tip``, спрямована вздовж (dx, dy)."""
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        back = QPointF(tip.x() - 6 * dx, tip.y() - 6 * dy)
        p.drawPolygon(QPolygonF([tip, QPointF(back.x() - 2 * dy, back.y() + 2 * dx),
                                 QPointF(back.x() + 2 * dy, back.y() - 2 * dx)]))
        p.restore()

    def _dim(self, p, a, b, text, ext=None, hit=None, side=-1, color=None, beside=0):
        """Розмірна лінія a–b (горизонтальна чи вертикальна) з підписом.

        ``beside`` — підпис горизонтального розміру на продовженні лінії:
        1 — праворуч від b, −1 — ліворуч від a.

        ``ext`` — координата предмета, від якої йдуть виносні лінії; ``side``
        −1 — підпис над лінією (ліворуч), 1 — під нею (праворуч)."""
        color = ACTIVE if hit is not None and self._is_active(*hit) else (color or INK)
        horizontal = abs(a.y() - b.y()) < 0.01
        p.save()
        p.setPen(QPen(color, 1))
        p.drawLine(a, b)
        if ext is not None:
            p.setPen(QPen(_alpha(color, 130), 1))
            for q in (a, b):
                if horizontal:
                    over = 4 if q.y() >= ext else -4
                    p.drawLine(QPointF(q.x(), ext), QPointF(q.x(), q.y() + over))
                else:
                    over = 4 if q.x() >= ext else -4
                    p.drawLine(QPointF(ext, q.y()), QPointF(q.x() + over, q.y()))
        p.restore()
        size = abs(b.x() - a.x()) + abs(b.y() - a.y())
        if size > 0.01:
            # На короткому розмірі стрілки стають ззовні.
            sign = 1 if size >= 16 else -1
            dx, dy = (b.x() - a.x()) / size, (b.y() - a.y()) / size
            self._arrow(p, b, dx * sign, dy * sign, color)
            self._arrow(p, a, -dx * sign, -dy * sign, color)
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        if beside:
            q = b if beside > 0 else a
            self._text(p, q.x() + beside * 10, q.y(), text, color, True,
                       "l" if beside > 0 else "r", hit)
        elif horizontal:
            self._text(p, mid.x(), mid.y() + side * (ROW / 2 + 1), text, color, True, "c", hit)
        else:
            self._text(p, mid.x() + side * 5, mid.y(), text, color, True,
                       "l" if side > 0 else "r", hit)


class JointDrawing(_Drawing):
    """Переріз стику A–B і вид на пласть A з усіма отворами кріплення."""

    LEFT, RIGHT = 118.0, 74.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.holes, self.ta, self.tb = [], 16.0, 16.0
        self.setMinimumSize(360, 430)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(450, 560)

    def set_data(self, holes, ta, tb):
        self.holes, self.ta, self.tb = holes, ta, tb
        self.update()

    # ---- геометрія, мм: x — від площини стику вглиб A, y — по товщині A ----
    def plane(self):
        """Зсув уздовж стику, через який проведено переріз."""
        row = self.active[0]
        if 0 <= row < len(self.holes):
            return self.holes[row]["along"]
        return min((h["along"] for h in self.holes), key=abs, default=0.0)

    def reach(self):
        """Скільки мм панелі A показати (вглиб від торця)."""
        ends = [40.0]
        for h in self.holes:
            if h["where"] == "edge":
                ends.append(h["depth"] or 0.0)
            elif h["where"] == "inner_face":
                ends.append(h["from_edge"] + h["d"] / 2)
        return max(ends) * 1.2 + 6

    def section_rect(self, h):
        """Отвір на перерізі: (x0, x1, y0, y1), мм; y = 0 — вісь товщини A."""
        r, depth = h["d"] / 2, h["depth"]
        if h["where"] == "edge":
            return 0.0, self.reach() if depth is None else depth, -r, r
        if h["where"] == "inner_face":
            top = self.ta / 2
            return (h["from_edge"] - r, h["from_edge"] + r,
                    top - (self.ta if depth is None else depth), top)
        depth = self.tb if depth is None else depth
        if h["where"] == "joint_face":
            return -depth, 0.0, -r, r
        return -self.tb, -self.tb + depth, -r, r

    def plan_rect(self, h):
        """Отвір на виді на пласть A: (x0, x1, v0, v1), v — уздовж стику."""
        r = h["d"] / 2
        x0, x1, _y0, _y1 = self.section_rect(h)
        return x0, x1, h["along"] - r, h["along"] + r

    # ---- малювання ----
    def draw(self, p):
        holes = self.holes
        edge = [i for i, h in enumerate(holes) if h["where"] == "edge"]
        inner = [i for i, h in enumerate(holes) if h["where"] == "inner_face"]
        in_b = [i for i, h in enumerate(holes) if h["where"] not in A_HOLES]
        along = [h["along"] for h in holes] or [0.0]
        radius = max([h["d"] / 2 for h in holes] or [4.0])
        v0, v1 = min(0.0, *along) - radius, max(0.0, *along) + radius
        insets = sorted({holes[i]["from_edge"] for i in inner})

        # Незмінні за висотою частини; решта — під масштаб.
        top_labels = len(inner) * ROW + 12
        low_labels = max(len(edge) * ROW + 14, 24.0)
        up = max(44.0, top_labels)
        fixed = 24 + up + low_labels + 34 + 12 + 14 + 34 + len(insets) * 20 + 12
        reach = self.reach()
        s = min((self.width() - self.LEFT - self.RIGHT) / (self.tb + reach),
                (self.height() - fixed) / (self.ta + v1 - v0), 7.0)
        s = max(s, 0.3)
        ox = self.LEFT + self.tb * s
        right = ox + reach * s
        half = self.ta / 2 * s
        yc = 24 + up + half
        b_top, b_bottom = 24.0, yc + half + low_labels
        plan_title = b_bottom + 34 + 12
        plan = QRectF(ox - self.tb * s, plan_title + 14, (self.tb + reach) * s,
                      max((v1 - v0) * s + 34, 100.0))
        # Вісь кріплення на виді; місце знизу — під літери A і B.
        oy = plan.top() + (plan.height() - 14 - (v1 - v0) * s) / 2 - v0 * s

        # -- переріз --
        plane = self.plane()
        self._title(p, 12, "Переріз стику" + (f" (зсув {num(plane)} мм)" if plane else ""))
        rect_b = QRectF(ox - self.tb * s, b_top, self.tb * s, b_bottom - b_top)
        rect_a = QRectF(ox, yc - half, right - ox, 2 * half)
        self._panel(p, rect_b, B_FILL, B_INK, "lr", Qt.BDiagPattern)
        self._panel(p, rect_a, A_FILL, A_INK, "ltb", Qt.FDiagPattern)
        self._text(p, rect_b.center().x(), b_bottom - 11, "B", INK, True, "c")
        self._text(p, right - 12, yc + half - 10, "A", INK, True, "c")

        rects = {i: self._px(self.section_rect(h), ox, yc, s, -1) for i, h in enumerate(holes)}
        for i in self._order(rects):
            behind = abs(holes[i]["along"] - plane) > 0.05
            self._hole(p, i, rects[i], dashed=behind)
        self._axis(p, QPointF(ox - self.tb * s - 8, yc), QPointF(right + 8, yc))

        for n, i in enumerate(in_b):
            y = yc + (n - (len(in_b) - 1) / 2) * ROW
            r = rects[i]
            self._label(p, i, 8, y, QPointF(max(r.left(), rect_b.left()), self._near(r, y)),
                        from_right=True)
        x = min(max([rects[i].center().x() for i in inner] or [0.0]) + 12, self.width() - 96.0)
        for n, i in enumerate(inner):
            y = 30 + n * ROW
            self._label(p, i, x, y, QPointF(rects[i].center().x(), rects[i].top()))
        # Під A: глибші — вище, тоді виноски не перетинаються.
        edge.sort(key=lambda i: -rects[i].right())
        x = min(max([rects[i].right() for i in edge] or [0.0]) + 8, self.width() - 96.0)
        for n, i in enumerate(edge):
            y = yc + half + 16 + n * ROW
            self._label(p, i, x, y, QPointF(min(rects[i].right() - 3, x - 8), rects[i].bottom()))
        row = self.active[0]
        if row in rects:
            self._active_dims(p, row, rects[row], rect_a, rect_b)
        self._dim(p, QPointF(right + 44, yc + half), QPointF(right + 44, yc - half),
                  num(self.ta), ext=right, side=1)
        if edge or in_b:
            self._dim(p, QPointF(right + 12, yc), QPointF(right + 12, yc - half),
                      num(self.ta / 2), ext=right, side=1, color=MUTED)
        self._dim(p, QPointF(rect_b.left(), b_bottom + 12), QPointF(ox, b_bottom + 12),
                  num(self.tb), ext=b_bottom, side=1)

        # -- вид на пласть A --
        self._title(p, plan_title, "Вид на пласть A (зсередини)")
        self._panel(p, QRectF(plan.left(), plan.top(), self.tb * s, plan.height()),
                    B_FILL, B_INK, "lr")
        self._panel(p, QRectF(ox, plan.top(), right - ox, plan.height()), A_FILL, A_INK, "l")
        self._text(p, ox - self.tb * s / 2, plan.bottom() - 11, "B", INK, True, "c")
        self._text(p, right - 12, plan.bottom() - 11, "A", INK, True, "c")
        rects = {i: self._px(self.plan_rect(h), ox, oy, s, 1) for i, h in enumerate(holes)}
        for i in self._order(rects):
            round_ = holes[i]["where"] == "inner_face"
            self._hole(p, i, rects[i], dashed=not round_, round_=round_)
        for v in sorted({0.0, *along}):
            y = oy + v * s
            self._axis(p, QPointF(plan.left() - 8, y), QPointF(right + 8, y))
        shifts = sorted({v for v in along if v}, key=abs)
        for n, v in enumerate(shifts):
            row = self._row_of("along", v)
            x = plan.left() - 16 - (n % 3) * 30
            self._dim(p, QPointF(x, oy), QPointF(x, oy + v * s), num(v), ext=plan.left(),
                      hit=(row, "along"))
        for n, v in enumerate(insets):
            row = next(i for i in inner if holes[i]["from_edge"] == v)
            y = plan.bottom() + 18 + n * 20
            self._dim(p, QPointF(ox, y), QPointF(ox + v * s, y), num(v), ext=plan.bottom(),
                      hit=(row, "from_edge"))
        # Куди «до середини стику» (туди відкладається додатний зсув).
        x = right + 26
        p.setPen(QPen(MUTED, 1))
        p.drawLine(QPointF(x, plan.top() + 6), QPointF(x, plan.bottom() - 6))
        self._arrow(p, QPointF(x, plan.bottom() - 6), 0, 1, MUTED)
        p.save()
        p.translate(x + 12, plan.center().y())
        p.rotate(90)
        self._text(p, 0, 0, "до середини", MUTED, align="c")
        p.restore()

    def _row_of(self, key, value):
        row = self.active[0]
        if 0 <= row < len(self.holes) and self.holes[row][key] == value:
            return row
        return next(i for i, h in enumerate(self.holes) if h[key] == value)

    @staticmethod
    def _px(rect, ox, oy, s, sign):
        x0, x1, y0, y1 = rect
        return QRectF(QPointF(ox + x0 * s, oy + sign * y0 * s),
                      QPointF(ox + x1 * s, oy + sign * y1 * s)).normalized()

    @staticmethod
    def _near(r, y):
        return min(max(y, r.top() + 2), r.bottom() - 2)

    def _order(self, rects):
        """Більші — нижче, активний — зверху."""
        return sorted(rects, key=lambda i: (i == self.active[0],
                                            -rects[i].width() * rects[i].height()))

    def _color(self, i):
        if i == self.active[0]:
            return ACTIVE
        return A_INK if self.holes[i]["where"] in A_HOLES else B_INK

    def _panel(self, p, r, fill, ink, solid, hatch=None):
        """Панель: суцільні — кромки з ``solid`` (l, r, t, b), решта — обрив."""
        p.fillRect(r, fill)
        if hatch is not None:
            p.fillRect(r, QBrush(_alpha(ink, 45), hatch))
        for side, a, b in (("l", r.topLeft(), r.bottomLeft()), ("r", r.topRight(), r.bottomRight()),
                           ("t", r.topLeft(), r.topRight()), ("b", r.bottomLeft(), r.bottomRight())):
            p.setPen(QPen(INK, 1.6) if side in solid else QPen(MUTED, 1, Qt.DashLine))
            p.drawLine(a, b)

    def _hole(self, p, i, r, dashed=False, round_=False):
        color = self._color(i)
        p.save()
        p.setPen(QPen(color, 1.8 if i == self.active[0] else 1.3,
                      Qt.DashLine if dashed else Qt.SolidLine))
        p.setBrush(_alpha(color, 30 if dashed else 60))
        if round_:
            p.drawEllipse(r)
        else:
            p.drawRect(r)
        p.restore()
        self.hits.append((r, i, "d"))

    def _axis(self, p, a, b):
        p.save()
        p.setPen(QPen(MUTED, 1, Qt.DashDotLine))
        p.drawLine(a, b)
        p.restore()

    def _label(self, p, i, x, y, target, from_right=False):
        """«#n ⌀8 × 25» з виноскою до отвору; ⌀ і глибина клікаються окремо."""
        h = self.holes[i]
        color = self._color(i)
        r = self._text(p, x, y, f"#{i + 1} ", MUTED, hit=None)
        r = self._text(p, r.right(), y, f"⌀{num(h['d'])}", color, True, hit=(i, "d"))
        depth = "наскр." if h["depth"] is None else f"× {num(h['depth'])}"
        r = self._text(p, r.right() + 4, y, depth, color, True, hit=(i, "depth"))
        p.save()
        p.setPen(QPen(color, 1))
        right = from_right or target.x() > r.right() + 3
        start = QPointF(r.right() + 3 if right else x - 3, y)
        p.drawLine(start, target)
        p.setBrush(color)
        p.drawEllipse(target, 2, 2)
        p.restore()

    def _active_dims(self, p, i, r, rect_a, rect_b):
        """Діаметр і глибина активного отвору — розмірними лініями."""
        h = self.holes[i]
        depth = num(h["depth"]) if h["depth"] is not None else "наскр."
        d = f"⌀{num(h['d'])}"
        if h["where"] == "inner_face":
            x = r.right() + 12
            self._dim(p, QPointF(x, r.bottom()), QPointF(x, r.top()), depth, ext=r.right(),
                      side=1, color=ACTIVE, hit=(i, "depth"))
            y = rect_a.top() - 5
            self._dim(p, QPointF(r.left(), y), QPointF(r.right(), y), "", ext=rect_a.top(),
                      color=ACTIVE)
            return
        # Глибина — над панеллю B, щоб не перекривати штрихування A.
        y = rect_a.top() - 10 if h["where"] == "edge" else rect_b.top() + 34
        self._dim(p, QPointF(r.left(), y), QPointF(r.right(), y), depth, ext=r.top(),
                  color=ACTIVE, hit=(i, "depth"))
        x = r.right() + 8 if h["where"] == "edge" else rect_b.left() - 6
        self._dim(p, QPointF(x, r.bottom()), QPointF(x, r.top()), d if h["where"] == "edge" else "",
                  ext=r.right() if h["where"] == "edge" else r.left(), side=1, color=ACTIVE,
                  hit=(i, "d") if h["where"] == "edge" else None)


class PlacementDrawing(_Drawing):
    """Точки кріплення вздовж стику-прикладу. Ключі кліків — поля кріплення."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.f, self.length = None, 720.0
        self.setMinimumSize(220, 132)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        return QSize(340, 150)

    def set_data(self, f, length):
        self.f, self.length = f, length
        self.update()

    def points(self):
        """``(точки, причина)`` — як у :func:`.fasteners.candidates`."""
        f = self.f
        if not f or not f["holes"]:
            return [], "Немає жодного отвору"
        if self.length < f.get("min_joint", 0.0) - 1e-6:
            return [], f"Стик {num(self.length)} мм < {num(f['min_joint'])} мм"
        pts = fasteners.positions(self.length, f["offset"], f["step"],
                                  max(h["d"] for h in f["holes"]), f.get("min_step", 0.0))
        # Кріплення, чий отвір вийшов би за кінець стику, не ставиться.
        pts = [u for u in pts if all(0.0 <= v <= self.length for v in self.offsets(u))]
        return pts, "" if pts else f"Стик {num(self.length)} мм закороткий"

    def offsets(self, u):
        """Де вздовж стику стають отвори кріплення з точкою ``u``."""
        to_middle = 1.0 if u < self.length / 2 else -1.0
        return sorted({u + to_middle * h["along"] for h in self.f["holes"]})

    def draw(self, p):
        x0, x1 = 24.0, self.width() - 24.0
        s = (x1 - x0) / max(self.length, 1.0)
        top, bottom = 40.0, max(64.0, self.height() - 58.0)
        pts, reason = self.points()
        self._panel_strip(p, QRectF(QPointF(x0, top), QPointF(x1, bottom)))
        self._dim(p, QPointF(x0, bottom + 40), QPointF(x1, bottom + 40), num(self.length),
                  ext=bottom, side=-1, hit=(-1, "length"))
        if reason:
            self._text(p, (x0 + x1) / 2, (top + bottom) / 2, reason, B_INK, True, "c")
            return
        y = bottom - min(12.0, (bottom - top) / 2)
        for u in pts:
            for v in self.offsets(u):
                main = abs(v - u) < 0.05
                p.setPen(QPen(A_INK, 1.2))
                p.setBrush(_alpha(A_INK, 130 if main else 30))
                r = 4.5 if main else 3.0
                p.drawEllipse(QPointF(x0 + v * s, y), r, r)
        # Крок скрізь однаковий: на тісних розмірах підписується лише перший.
        for n, (a, b) in enumerate(zip(pts, pts[1:])):
            text = num(b - a) if n == 0 or (b - a) * s >= 44 else ""
            self._dim(p, QPointF(x0 + a * s, 24), QPointF(x0 + b * s, 24), text,
                      ext=y, hit=(-1, "step"), side=-1)
        self._dim(p, QPointF(x0, bottom + 20), QPointF(x0 + pts[0] * s, bottom + 20),
                  num(pts[0]), ext=bottom, hit=(-1, "offset"),
                  beside=1 if pts[0] * s < 40 else 0)
        if len(pts) > 1:
            self._dim(p, QPointF(x0 + pts[-1] * s, bottom + 20), QPointF(x1, bottom + 20),
                      num(self.length - pts[-1]), ext=bottom, hit=(-1, "offset"),
                      beside=-1 if (self.length - pts[-1]) * s < 40 else 0)

    def _panel_strip(self, p, r):
        p.fillRect(r, A_FILL)
        p.setPen(QPen(MUTED, 1, Qt.DashLine))
        p.drawLine(r.topLeft(), r.topRight())
        p.setPen(QPen(INK, 1.6))
        p.drawPolyline(QPolygonF([r.topLeft(), r.bottomLeft(), r.bottomRight(), r.topRight()]))
