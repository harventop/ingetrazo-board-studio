# SPDX-License-Identifier: GPL-3.0-or-later
"""Матеріали плит і текстури: пласті — імітація дуба, торці — структура
серцевини (ДСП або МДФ/ДВП).

Щоб додати плиту — допишіть рядок у ``PRESETS``. Текстури генерує
``scripts/make_textures.py``.
"""
from __future__ import annotations

from pathlib import Path

from core.materials import Material

TEXTURES = Path(__file__).parent / "textures"

#: поверхня → (назва матеріалу в документі, файл, ширина плитки м, висота плитки м).
#: Ширина зображення (U) — вздовж волокон / довжини.
SURFACES = {
    "oak": ("Board Studio — Дуб", "oak.png", 0.8, 0.4),
    "chipboard": ("Board Studio — ДСП (торець)", "chipboard.png", 0.12, 0.12),
    "fibreboard": ("Board Studio — МДФ/ДВП (торець)", "fibreboard.png", 0.08, 0.08),
}

#: (назва, товщина мм, текстура торця)
PRESETS = (
    ("ДСП 10", 10.0, "chipboard"),
    ("ДСП 16", 16.0, "chipboard"),
    ("ДСП 18", 18.0, "chipboard"),
    ("ДСП 22", 22.0, "chipboard"),
    ("ДСП 25", 25.0, "chipboard"),
    ("ДСП 28", 28.0, "chipboard"),
    ("ДСП 38", 38.0, "chipboard"),
    ("МДФ 6", 6.0, "fibreboard"),
    ("МДФ 10", 10.0, "fibreboard"),
    ("МДФ 16", 16.0, "fibreboard"),
    ("МДФ 18", 18.0, "fibreboard"),
    ("МДФ 19", 19.0, "fibreboard"),
    ("МДФ 22", 22.0, "fibreboard"),
    ("ДВП 3", 3.0, "fibreboard"),
    ("ДВП 4", 4.0, "fibreboard"),
)
DEFAULT = "ДСП 16"
_BY_NAME = {name: (mm, edge) for name, mm, edge in PRESETS}


def preset_thickness(name):
    """Номінальна товщина плити, мм."""
    return _BY_NAME.get(name, _BY_NAME[DEFAULT])[0]


def edge_surface(name):
    return _BY_NAME.get(name, _BY_NAME[DEFAULT])[1]


def _texture(surface):
    _name, file, sw, sh = SURFACES[surface]
    return {"path": str(TEXTURES / file), "sw": sw, "sh": sh}


def ensure_materials(scene, material):
    """Зареєструвати в документі матеріали плити (видно в панелі матеріалів)."""
    for surface in ("oak", edge_surface(material)):
        name = SURFACES[surface][0]
        if name not in scene.materials:
            scene.materials[name] = Material(name, texture=_texture(surface))


def paint(surface, along, across):
    """Атрибути грані: текстура ``surface``, волокна (вісь U) уздовж ``along``,
    вісь V — уздовж ``across`` (обидва одиничні, у площині грані)."""
    tex = _texture(surface)
    tex["uvw"] = [along.x() / tex["sw"], along.y() / tex["sw"], along.z() / tex["sw"], 0.0,
                  across.x() / tex["sh"], across.y() / tex["sh"], across.z() / tex["sh"], 0.0]
    return {"mat": SURFACES[surface][0], "texture": tex}


def board_paints(corners, push, material):
    """Атрибути для шести граней ``box_loops(corners, push)`` у тому ж порядку:
    дві пласті (дуб уздовж довжини), потім чотири торці."""
    length = (corners[1] - corners[0]).normalized()
    width = (corners[3] - corners[0]).normalized()
    depth = push.normalized()
    edge = edge_surface(material)
    return ([paint("oak", length, width) for _ in range(2)]
            + [paint(edge, (corners[i] - corners[i - 1]).normalized(), depth) for i in range(4)])
