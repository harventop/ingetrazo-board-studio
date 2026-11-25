# SPDX-License-Identifier: GPL-3.0-or-later
"""Бібліотека плагіна: заведені кріплення й крайки.

Живе в налаштуваннях (``QSettings``, JSON), спільна для всіх документів.
Редагується у вікні «Налаштування Board Studio»; панелі «Кріплення» і
«Крайка» лише обирають із неї.

**Кріплення** — правила розстановки, обмеження й список присадок. Кожна
присадка прив'язана до точки кріплення на стику (торець деталі A лежить на
пласті деталі B):

- ``edge`` — отвір у торці A (по осі товщини);
- ``joint_face`` — у пласті B з боку стику;
- ``outer_face`` — у пласті B з протилежного боку (наскрізний конфірмат);
- ``inner_face`` — у пласті A з внутрішнього боку, ``from_edge`` мм від торця
  (чашка мініфікса).

``along`` — зсув від точки кріплення до середини стику (шкант біля
мініфікса — 32). ``depth`` ``None`` — наскрізний.

**Крайка** — назва, товщина (зменшує контур різу), колір (підсвітка в режимі
крайки) і артикул (для довідки: у DXF матеріал крайки не передається).
"""
from __future__ import annotations

import copy
import json
import re

from PySide6.QtCore import QSettings

from .i18n import N_, tr, variants

KEY = "board_studio/library"
WHERE = (("edge", N_("Panel edge")),
         ("joint_face", N_("Other panel's face (joint)")),
         ("outer_face", N_("Other panel's face (outer)")),
         ("inner_face", N_("Panel's own face (inner)")))
#: Типова група ABF для присадки (атрибут ``Skp_GroupInstanceName``).
DEFAULT_GROUP = {"edge": "_ABF_sideDrill", "joint_face": "_ABF_dowel",
                 "outer_face": "_ABF_screwInside", "inner_face": "_ABF_minifixBolts"}


def hole(where, d, depth, along=0.0, from_edge=0.0, article="", group="", layer=""):
    return {"where": where, "d": d, "depth": depth, "along": along, "from_edge": from_edge,
            "article": article, "group": group, "layer": layer}


#: Назви типових записів — англійською; показувані — :func:`default_fasteners`.
DEFAULT_FASTENERS = [
    {"key": "dowel_8x30", "name": N_("Dowel 8×30"),
     "offset": 32.0, "step": 256.0, "min_step": 64.0, "min_joint": 40.0,
     "min_edge_thickness": 16.0, "min_face_thickness": 16.0, "min_wall": 4.0,
     "holes": [hole("edge", 8.0, 25.0),
               hole("joint_face", 8.0, 12.0, article="38878", group="_ABF_dowel")]},
    {"key": "confirmat_7x50", "name": N_("Confirmat 7×50"),
     "offset": 37.0, "step": 256.0, "min_step": 64.0, "min_joint": 50.0,
     "min_edge_thickness": 16.0, "min_face_thickness": 16.0, "min_wall": 3.0,
     "holes": [hole("edge", 4.5, 34.0),
               hole("outer_face", 7.0, None, article="44817", group="_ABF_screwInside")]},
    {"key": "minifix_15", "name": N_("Minifix + dowel"),
     "offset": 37.0, "step": 512.0, "min_step": 128.0, "min_joint": 100.0,
     "min_edge_thickness": 16.0, "min_face_thickness": 16.0, "min_wall": 3.0,
     "holes": [hole("edge", 8.0, 33.0),
               hole("inner_face", 15.0, 13.0, from_edge=34.0, article="59042",
                    group="_ABF_minifixBolts"),
               hole("joint_face", 5.0, 12.0, group="_ABF_minifixPlasticBase",
                    layer="D8-DEPTH12-$38878"),
               hole("edge", 8.0, 25.0, along=32.0),
               hole("joint_face", 8.0, 12.0, along=32.0, article="38878",
                    group="_ABF_minifixPlasticBase")]},
]

DEFAULT_EDGES = [
    {"key": "pvc_04", "name": N_("PVC 0.4"), "thickness": 0.4, "color": "#4fa3e0", "article": ""},
    {"key": "pvc_08", "name": N_("PVC 0.8"), "thickness": 0.8, "color": "#3cb371", "article": ""},
    {"key": "pvc_10", "name": N_("PVC 1.0"), "thickness": 1.0, "color": "#e0a030", "article": ""},
    {"key": "pvc_20", "name": N_("PVC 2.0"), "thickness": 2.0, "color": "#d9534f", "article": ""},
]

FASTENER_FIELDS = (
    # (ключ, підпис, мін, макс) — числові поля кріплення, мм
    ("offset", N_("Offset from the joint ends"), 0.0, 1000.0),
    ("step", N_("Largest step"), 1.0, 5000.0),
    ("min_step", N_("Smallest step (gap between fasteners)"), 0.0, 5000.0),
    ("min_joint", N_("Shortest joint"), 0.0, 5000.0),
    ("min_edge_thickness", N_("Least thickness of the panel with the edge"), 0.0, 100.0),
    ("min_face_thickness", N_("Least thickness of the other panel"), 0.0, 100.0),
    ("min_wall", N_("Least wall beside a hole"), 0.0, 50.0),
)

_listeners = []


def _localized(items, defaults):
    """Типові назви — мовою інтерфейсу, хоч би якою їх було збережено; назви,
    які дав користувач, не чіпаємо."""
    names = {d["key"]: d["name"] for d in defaults}
    for item in items:
        name = names.get(item.get("key"))
        if name is not None and item.get("name") in variants(name):
            item["name"] = tr(name)
    return items


def default_fasteners():
    """Копія типових кріплень із назвами мовою інтерфейсу."""
    return _localized(copy.deepcopy(DEFAULT_FASTENERS), DEFAULT_FASTENERS)


def default_edges():
    return _localized(copy.deepcopy(DEFAULT_EDGES), DEFAULT_EDGES)


def load():
    """``{"fasteners": [...], "edges": [...]}`` — копія; типові, якщо порожньо."""
    raw = QSettings().value(KEY)
    data = None
    if raw:
        try:
            data = json.loads(str(raw))
        except ValueError:
            data = None
    if not isinstance(data, dict):
        data = {}
    out = {"fasteners": _localized(data.get("fasteners") or copy.deepcopy(DEFAULT_FASTENERS),
                                    DEFAULT_FASTENERS),
           "edges": _localized(data.get("edges") or copy.deepcopy(DEFAULT_EDGES),
                                DEFAULT_EDGES)}
    for f in out["fasteners"]:
        for key, _label, _lo, _hi in FASTENER_FIELDS:
            f.setdefault(key, 0.0)
        for h in f.setdefault("holes", []):
            for k, v in hole("edge", 0, 0).items():
                h.setdefault(k, v)
    return out


def save(data):
    """Зберегти (``None`` — повернути типові) і сповістити панелі."""
    qs = QSettings()
    if data is None:
        qs.remove(KEY)
    else:
        qs.setValue(KEY, json.dumps(data, ensure_ascii=False))
    for fn in list(_listeners):
        fn()


def on_change(fn):
    _listeners.append(fn)


def fasteners():
    return load()["fasteners"]


def edges():
    return load()["edges"]


def find(items, key):
    return next((i for i in items if i.get("key") == key), None)


def new_key(items, name):
    """Ключ для нового запису: з назви, унікальний."""
    base = re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_") or "item"
    taken = {i.get("key") for i in items}
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    return key
