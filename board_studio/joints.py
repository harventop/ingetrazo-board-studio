# SPDX-License-Identifier: GPL-3.0-or-later
"""Стики між панелями — геометрія для розстановки кріплення.

Стик — торець однієї панелі (A), що лежить на пласті іншої (B): площини
збігаються, нормалі протилежні. Математика — на :class:`.panels.Panel`
(світові осі й розміри, м), тож модуль легко перевірити без вікна.
"""
from __future__ import annotations

import numpy as np

PLANE_TOL = 0.0005      # м: торець «на» пласті, якщо площини ближчі за 0.5 мм
PARALLEL = 0.999


def side_frame(p, side):
    """Торець панелі у світі: (початок, напрямок уздовж, довжина, назовні)."""
    L, W, _T = p.size
    x, y = p.R[:, 0], p.R[:, 1]
    o = p.origin
    return [(o, x, L, -y), (o + x * L, y, W, x), (o + y * W, x, L, y), (o, y, W, -x)][side]


def _clip(q0, dq, lo, hi):
    """Відрізок q0 + dq·u, u∈[0,1] у межах прямокутника [lo, hi] (2D)."""
    u0, u1 = 0.0, 1.0
    for k in range(2):
        if abs(dq[k]) < 1e-12:
            if not lo[k] <= q0[k] <= hi[k]:
                return None
            continue
        a, b = (lo[k] - q0[k]) / dq[k], (hi[k] - q0[k]) / dq[k]
        if a > b:
            a, b = b, a
        u0, u1 = max(u0, a), min(u1, b)
    return (u0, u1) if u1 > u0 else None


def joints(a, b):
    """Стики «торець ``a`` на пласті ``b``»: ``[(side, top, u0, u1)]`` —
    відрізок торця (м від його початку), де лінія шкантів лежить на пласті."""
    out = []
    zb = b.R[:, 2]
    Lb, Wb, Tb = b.size
    for side in range(4):
        start, along, length, outward = side_frame(a, side)
        for top in (True, False):
            normal = zb if top else -zb
            if outward @ normal > -PARALLEL:
                continue
            plane = b.origin + zb * (Tb if top else 0.0)
            if abs((start - plane) @ zb) > PLANE_TOL:
                continue
            mid = start + a.R[:, 2] * (a.size[2] / 2)
            q0 = ((mid - b.origin) @ b.R)[:2]
            dq = ((along * length) @ b.R)[:2]
            span = _clip(q0, dq, np.zeros(2), np.array([Lb, Wb]))
            if span:
                out.append((side, top, span[0] * length, span[1] * length))
    return out


def hole_world(panel, hole):
    """Центр отвору у світі (м) і нормаль (куди дивиться отвір назовні)."""
    T = panel.mm[2]
    if hole["type"] == "face":
        z = T if hole.get("top", True) else 0.0
        n = panel.R[:, 2] * (1 if hole.get("top", True) else -1)
        return panel.to_world((hole["x"], hole["y"], z)), n
    z = hole.get("z")
    p = panel.to_world((hole["x"], hole["y"], T / 2 if z is None else z))
    return p, side_frame(panel, hole.get("side", 0))[3]
