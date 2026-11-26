# SPDX-License-Identifier: GPL-3.0-or-later
"""Локалізація плагіна — за тим самим принципом, що й ``core.i18n`` IngeTrazo.

Мова джерела — англійська: ключ :func:`tr` — сам англійський рядок. Решта мов —
плоскі словники ``{english: переклад}`` у ``locales/<мова>.json``. Мову обирає
користувач у самому IngeTrazo; якщо для неї немає словника або в словнику немає
рядка — показується англійський.

Щоб додати мову, покладіть ще один ``locales/<код>.json`` (код — як у IngeTrazo:
``de``, ``pt-BR``…).

Що НЕ перекладається, бо живе в документах, налаштуваннях чи DXF: ключі записів
бібліотеки, назви плит у ``data["material"]`` («ДСП 16» — див.
:func:`.materials.label`), назви груп «Panel N», усе в :mod:`.dxf`.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from core.i18n import current_language

LOCALES = Path(__file__).parent / "locales"


def N_(text):
    """Позначка рядка-константи, який перекладуть під час показу: ``tr(константа)``."""
    return text


@lru_cache(maxsize=None)
def catalog(lang):
    """Словник мови; порожній — якщо файлу немає або він пошкоджений."""
    path = LOCALES / f"{lang}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, AttributeError) as exc:
        logging.getLogger("ingetrazo.extensions").warning(
            "Board Studio: bad translation file %s: %s", path, exc)
        return {}


def languages():
    """Мови, для яких є словник (крім англійської)."""
    return sorted(p.stem for p in LOCALES.glob("*.json"))


def _lookup(text):
    lang = current_language()
    out = catalog(lang).get(text)
    if out is None and "-" in lang:             # «uk-UA» → «uk»
        out = catalog(lang.split("-")[0]).get(text)
    return out or text


def tr(text, /, **kwargs):
    """Рядок мовою інтерфейсу. ``{поля}`` підставляються лише тоді, коли їх
    передано; зіпсований переклад не валить плагін — береться англійський."""
    out = _lookup(text)
    if kwargs:
        try:
            return out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text.format(**kwargs)
    return out


def variants(text):
    """Рядок усіма мовами — упізнати типову назву, збережену іншою мовою."""
    return {text, *(c[text] for c in map(catalog, languages()) if text in c)}
