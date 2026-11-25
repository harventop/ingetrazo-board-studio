# SPDX-License-Identifier: GPL-3.0-or-later
"""Розстановка кріплення з бібліотеки (:mod:`.library`) у стиках панелей.

Кріплення — словник із бібліотеки: правила розстановки (відступ від кінців
стику, найбільший і найменший крок, найменша довжина стику), обмеження
(товщини деталей, товщина стінки біля отвору) і присадки. Тут лише
геометрія: де точки кріплення і куди стає кожна присадка. Отвори — у
локальних мм кожної панелі (див. :mod:`.panels`).
"""
from __future__ import annotations

import math

from .joints import joints, side_frame

TOL = 0.01      # мм: координати моделі — float32, товщина 16 може бути 15.9999


def positions(length, offset, step, d, min_step=0.0):
    """Точки кріплення (мм) уздовж стику довжиною ``length``: перша й
    остання — на ``offset`` від кінців, між ними рівно, крок не більший за
    ``step`` і, якщо можна, не менший за ``min_step``."""
    if length < 2 * d:
        return []
    if length < 2 * offset + d:
        return [length / 2]
    span = length - 2 * offset
    if span < min_step:
        return [length / 2]
    n = max(2, math.ceil(span / max(step, 1.0) - 1e-9) + 1)
    while n > 2 and span / (n - 1) < min_step:
        n -= 1
    return [offset + span * i / (n - 1) for i in range(n)]


def joint_id(a, b):
    return "fix:" + "|".join(sorted((a.group.uid, b.group.uid)))


def is_fastener(hole):
    """Отвір від кріплення (і старі шканти — ``dowel:``)."""
    return str(hole.get("joint", "")).startswith(("fix:", "dowel:"))


def check(f, a, b):
    """Причина, чому кріплення ``f`` не стає в стик «торець a — пласть b»,
    або ``None``."""
    if not f["holes"]:
        return "у кріпленні немає жодного отвору"
    ta, tb = a.mm[2], b.mm[2]
    wall = f.get("min_wall", 0.0)
    if ta < f.get("min_edge_thickness", 0.0) - TOL:
        return f"«{a.name}»: товщина {ta:g} мм < {f['min_edge_thickness']:g} мм"
    if tb < f.get("min_face_thickness", 0.0) - TOL:
        return f"«{b.name}»: товщина {tb:g} мм < {f['min_face_thickness']:g} мм"
    for h in f["holes"]:
        if h["where"] == "edge" and (ta - h["d"]) / 2 < wall - TOL:
            return (f"«{a.name}»: стінка біля отвору Ø{h['d']:g} у торці "
                    f"{(ta - h['d']) / 2:g} мм < {wall:g} мм")
        if h["where"] in ("joint_face", "outer_face", "inner_face") and h["depth"] is not None:
            t = ta if h["where"] == "inner_face" else tb
            if t - h["depth"] < wall - TOL:
                who = a.name if h["where"] == "inner_face" else b.name
                return (f"«{who}»: під отвором Ø{h['d']:g}×{h['depth']:g} лишається "
                        f"{t - h['depth']:g} мм < {wall:g} мм")
    return None


def _r(v):
    return round(float(v), 2)


def _inside(panel, x, y, r):
    L, W, _T = panel.mm
    return r - 1e-6 <= x <= L - r + 1e-6 and r - 1e-6 <= y <= W - r + 1e-6


class Candidate:
    """Рекомендоване місце кріплення на стику «торець a — пласть b».

    ``u`` — мм від початку стику; ``point`` — світова точка на лінії стику
    (середина товщини a), ``inward`` — у торець a; ``installed`` — тут уже
    стоїть кріплення."""

    def __init__(self, f, a, b, side, top, u0, length, u, kind, point, inward, along,
                 holes, installed):
        self.f, self.a, self.b, self.side, self.top = f, a, b, side, top
        self.u0, self.length, self.u, self.kind = u0, length, u, kind
        self.point, self.inward, self.along = point, inward, along
        self.holes, self.installed = holes, installed
        self.joint = joint_id(a, b)
        self.key = (self.joint, side, bool(top), round(u, 1))

    @property
    def label(self):
        where = "край" if self.kind == "end" else "середина"
        return f"{self.a.name} → {self.b.name}: {self.u:g} мм ({where})"


def candidates(panels, f, offset=None, step=None):
    """Усі можливі місця кріплення ``f`` між ``panels``: на ``offset`` від
    кінців кожного стику, а на довгих стиках — ще й посередині з кроком
    не більшим за ``step`` (типово — з бібліотеки).

    Повертає ``(candidates, skipped)``; ``skipped`` — ``[(назви, причина)]``
    для стиків, куди це кріплення не стає."""
    offset = f["offset"] if offset is None else offset
    step = f["step"] if step is None else step
    out, skipped = [], []
    for a in panels:
        for b in panels:
            if a is b:
                continue
            for side, top, u0, u1 in joints(a, b):
                length = (u1 - u0) * 1000
                reason = check(f, a, b)
                if reason is None and length < f.get("min_joint", 0.0) - TOL:
                    reason = f"стик {length:g} мм < {f['min_joint']:g} мм"
                points = [] if reason else positions(length, offset, step,
                                                     max(h["d"] for h in f["holes"]),
                                                     f.get("min_step", 0.0))
                if reason is None and not points:
                    reason = f"стик {length:g} мм закороткий"
                if reason:
                    skipped.append((f"{a.name} — {b.name}", reason))
                    continue
                out += _joint_candidates(f, a, b, side, top, u0, length, points)
    return out, skipped


def _occupied(a, side, joint, x, y, near):
    """Чи стоїть уже кріплення біля точки (x, y) торця ``side`` панелі a."""
    for h in a.data.get("holes", []):
        if (h.get("type") == "side" and h.get("side") == side and is_fastener(h)
                and math.hypot(h["x"] - x, h["y"] - y) < near):
            return True
    return False


def _joint_candidates(f, a, b, side, top, u0, length, points):
    start, along, _len, outward = side_frame(a, side)
    mid = start + a.R[:, 2] * (a.size[2] / 2)
    inward = -outward
    # Внутрішній бік A — той, куди від A лежить B.
    a_centre = a.to_world(tuple(v / 2 for v in a.mm))
    b_centre = b.to_world(tuple(v / 2 for v in b.mm))
    inner_top = float((b_centre - a_centre) @ a.R[:, 2]) >= 0
    near = max(max(h["d"] for h in f["holes"]), 8.0)
    out = []
    for i, u in enumerate(points):
        batch = _batch(f, a, b, side, top, inner_top, mid, along, inward, u0, length, u)
        if batch is None:
            continue
        p = mid + along * (u0 + u / 1000)
        x, y, _z = a.to_local_mm(p)
        kind = "end" if i in (0, len(points) - 1) else "middle"
        out.append(Candidate(f, a, b, side, top, u0, length, u, kind, p, inward, along, batch,
                             _occupied(a, side, joint_id(a, b), x, y, near)))
    return out


def _batch(f, a, b, side, top, inner_top, mid, along, inward, u0, length, u):
    """Отвори одного кріплення в точці u — ``[(panel, hole)]`` або ``None``,
    якщо якийсь отвір вийшов би за край."""
    to_middle = 1.0 if u < length / 2 else -1.0
    batch = []
    for h in f["holes"]:
        uu = u + to_middle * h.get("along", 0.0)
        if not 0.0 <= uu <= length:
            return None
        p = mid + along * (u0 + uu / 1000)
        where = h["where"]
        if where == "edge":
            x, y, z = a.to_local_mm(p)
            batch.append((a, {"type": "side", "side": side, "x": _r(x), "y": _r(y),
                              "z": _r(z), "d": h["d"], "depth": h["depth"]}))
            continue
        if where == "inner_face":
            panel, face_top = a, inner_top
            p = p + inward * (h.get("from_edge", 0.0) / 1000)
        else:
            panel, face_top = b, (top if where == "joint_face" else not top)
        x, y, _z = panel.to_local_mm(p)
        if not _inside(panel, x, y, h["d"] / 2):
            return None
        hole = {"type": "face", "x": _r(x), "y": _r(y), "top": face_top, "d": h["d"],
                "depth": h["depth"], "article": h.get("article", "")}
        if h.get("group"):
            hole["group"] = h["group"]
        if h.get("layer"):
            hole["layer"] = h["layer"]
        batch.append((panel, hole))
    return batch


def holes_for(chosen):
    """``{id(group): [hole]}`` для обраних кандидатів (вже встановлені —
    пропускаються)."""
    out = {}
    for c in chosen:
        if c.installed:
            continue
        base = {"joint": c.joint, "fastener": c.f.get("key", ""),
                "fastener_name": c.f.get("name", "")}
        for panel, hole in c.holes:
            out.setdefault(id(panel.group), []).append({**hole, **base})
    return out


def plan(panels, f, offset=None, step=None):
    """Усі рекомендовані місця разом: ``(holes, pairs, skipped)``."""
    cands, skipped = candidates(panels, f, offset, step)
    return holes_for(cands), {c.joint for c in cands}, skipped
