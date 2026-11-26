# SPDX-License-Identifier: GPL-3.0-or-later
"""Матеріали плит і текстури: пласті — імітація дуба, торці — структура
серцевини (ДСП або МДФ/ДВП).

Щоб додати плиту — допишіть рядок у ``PRESETS``. Текстури генерує
``scripts/make_textures.py``.
"""
from __future__ import annotations

from pathlib import Path

from core.materials import Material

from .i18n import N_, tr

TEXTURES = Path(__file__).parent / "textures"

#: поверхня → (назва матеріалу в документі, файл, ширина плитки м, висота плитки м).
#: Назва потрапляє в документ мовою, якою його малювали (:func:`surface_name`).
#: Ширина зображення (U) — вздовж волокон / довжини.
SURFACES = {
    "oak": (N_("Board Studio — Oak"), "oak.png", 0.8, 0.4),
    "chipboard": (N_("Board Studio — Chipboard (edge)"), "chipboard.png", 0.12, 0.12),
    "fibreboard": (N_("Board Studio — MDF/Hardboard (edge)"), "fibreboard.png", 0.08, 0.08),
}

#: (назва, товщина мм, текстура торця). Назва — ключ: записана в документах і
#: налаштуваннях, тому не перекладається; підпис для неї дає :func:`label`.
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
#: Однотонний декор — для панелей без текстури (напрямок «none»).
PLAIN = (N_("Board Studio — Plain"), (0.93, 0.92, 0.89))
_BY_NAME = {name: (mm, edge) for name, mm, edge in PRESETS}


#: Вид плити в ключі → підпис.
_KINDS = {"ДСП": N_("Chipboard"), "МДФ": N_("MDF"), "ДВП": N_("Hardboard")}


def label(name):
    """Підпис плити мовою інтерфейсу: «ДСП 16» → «Chipboard 16». Назва не з
    ``PRESETS`` показується як є."""
    if name not in _BY_NAME:
        return name
    kind, _sp, rest = name.partition(" ")
    return f"{tr(_KINDS[kind])} {rest}" if kind in _KINDS else name


def surface_name(surface):
    return tr(SURFACES[surface][0])


def plain_name():
    return tr(PLAIN[0])


def preset_thickness(name):
    """Номінальна товщина плити, мм."""
    return _BY_NAME.get(name, _BY_NAME[DEFAULT])[0]


def edge_surface(name):
    return _BY_NAME.get(name, _BY_NAME[DEFAULT])[1]


def _texture(surface):
    _name, file, sw, sh = SURFACES[surface]
    return {"path": str(TEXTURES / file), "sw": sw, "sh": sh}


def ensure_materials(scene, material, plain=False):
    """Зареєструвати в документі матеріали плити (видно в панелі матеріалів);
    ``plain`` — ще й однотонний декор."""
    if material is not None:
        for surface in ("oak", edge_surface(material)):
            name = surface_name(surface)
            if name not in scene.materials:
                scene.materials[name] = Material(name, texture=_texture(surface))
    if plain and plain_name() not in scene.materials:
        scene.materials[plain_name()] = Material(plain_name(), color=PLAIN[1])


def paint_plain():
    return {"mat": plain_name(), "color": list(PLAIN[1])}


def paint(surface, along, across):
    """Атрибути грані: текстура ``surface``, волокна (вісь U) уздовж ``along``,
    вісь V — уздовж ``across`` (обидва одиничні, у площині грані)."""
    tex = _texture(surface)
    tex["uvw"] = [along.x() / tex["sw"], along.y() / tex["sw"], along.z() / tex["sw"], 0.0,
                  across.x() / tex["sh"], across.y() / tex["sh"], across.z() / tex["sh"], 0.0]
    return {"mat": surface_name(surface), "texture": tex}


def board_paints(corners, push, material):
    """Атрибути для шести граней ``box_loops(corners, push)`` у тому ж порядку:
    дві пласті (дуб уздовж довжини), потім чотири торці."""
    length = (corners[1] - corners[0]).normalized()
    width = (corners[3] - corners[0]).normalized()
    depth = push.normalized()
    edge = edge_surface(material)
    return ([paint("oak", length, width) for _ in range(2)]
            + [paint(edge, (corners[i] - corners[i - 1]).normalized(), depth) for i in range(4)])
