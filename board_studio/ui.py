# SPDX-License-Identifier: GPL-3.0-or-later
"""Команди для деталей: властивості (кромка, текстура, декор), шканти,
експорт DXF для ViyarPro."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
                               QVBoxLayout, QWidget)

from . import fasteners, holemarks
from .dxf import export
from . import library

from .panels import all_panels, selected_panels, update_panels

GRAIN_LABELS = (("length", "Along length"), ("width", "Along width"), ("none", "No texture"))
KEEP = "(keep)"


def _status(viewport, text, msec=5000):
    flash = getattr(viewport, "flash_status", None)
    if callable(flash):
        flash(text, msec)


def _need_panels(app, panels, what):
    if panels:
        return True
    QMessageBox.information(app.window, "Board Studio",
                            f"Select one or more Board Studio panels to {what}.")
    return False


# ---- Властивості: кромка, текстура, декор ----------------------------------------------

def _same(values):
    values = list(values)
    return values[0] if values and all(v == values[0] for v in values) else KEEP


class PropertiesDialog(QDialog):
    """Напрямок текстури й декор Viyar для виділених панелей (крайка —
    у режимі «Крайка»). Поле, де панелі розходяться, показує «(keep)» і їх
    не змінює."""

    def __init__(self, parent, panels):
        super().__init__(parent)
        self.setWindowTitle("Panel Properties" if len(panels) == 1
                            else f"Panel Properties — {len(panels)} panels")
        datas = [p.data for p in panels]
        lay = QVBoxLayout(self)

        decor = QGroupBox("Decor (Viyar)", self)
        form = QFormLayout(decor)
        self.article = QLineEdit(self)
        self.decor = QLineEdit(self)
        for edit, key, hint in ((self.article, "article", "e.g. 151932"),
                                (self.decor, "decor", "e.g. KRONOSPAN 5307 SN")):
            value = _same(d[key] for d in datas)
            if value == KEEP:
                edit.setPlaceholderText("(mixed — leave empty to keep)")
            else:
                edit.setText(value)
                edit.setPlaceholderText(hint)
        form.addRow("Article", self.article)
        form.addRow("Name", self.decor)
        self.grain = QComboBox(self)
        grain = _same(d["grain"] for d in datas)
        if grain == KEEP:
            self.grain.addItem(KEEP, KEEP)
        for key, label in GRAIN_LABELS:
            self.grain.addItem(label, key)
        self.grain.setCurrentIndex(self.grain.findData(grain))
        form.addRow("Texture direction", self.grain)
        lay.addWidget(decor)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def apply_to(self, data):
        """Нові дані панелі з полів діалогу (``data`` не змінюється)."""
        new = copy.deepcopy(data)
        for edit, key in ((self.article, "article"), (self.decor, "decor")):
            if edit.text() or edit.isModified():
                new[key] = edit.text().strip().lstrip("$") if key == "article" else edit.text().strip()
        if self.grain.currentData() != KEEP:
            new["grain"] = self.grain.currentData()
        return new


def edit_properties(app):
    vp = app.viewport
    panels = selected_panels(vp.scene)
    if not _need_panels(app, panels, "set the texture and decor"):
        return
    dlg = PropertiesDialog(app.window, panels)
    if dlg.exec() != QDialog.Accepted:
        return
    err = update_panels(vp, [(p, dlg.apply_to(p.data)) for p in panels])
    _status(vp, f"Panel properties not changed: {err}" if err else
            f"Panel properties set for {len(panels)} panel(s)")


# ---- Кріплення ---------------------------------------------------------------------------

def fastener_summary(f):
    """Опис кріплення з бібліотеки для панелі й підказки."""
    where = dict(library.WHERE)
    lines = []
    for h in f["holes"]:
        depth = "наскрізь" if h["depth"] is None else f"{h['depth']:g}"
        extra = []
        if h.get("along"):
            extra.append(f"+{h['along']:g} до середини")
        if h.get("from_edge"):
            extra.append(f"{h['from_edge']:g} від торця")
        art = f" ${h['article']}" if h.get("article") else ""
        lines.append(f"• {where.get(h['where'], h['where'])}: Ø{h['d']:g} × {depth}{art}"
                     + (f" ({', '.join(extra)})" if extra else ""))
    lines.append(f"Відступ {f['offset']:g} мм, крок {f.get('min_step', 0):g}…{f['step']:g} мм, "
                 f"стик ≥ {f.get('min_joint', 0):g} мм.")
    lines.append(f"Товщина деталей ≥ {f.get('min_edge_thickness', 0):g} / "
                 f"{f.get('min_face_thickness', 0):g} мм, стінка ≥ {f.get('min_wall', 0):g} мм.")
    return "\n".join(lines)


def add_candidates(app, chosen):
    """Встановити обрані рекомендовані місця (один крок undo); текст результату."""
    vp = app.viewport
    new = fasteners.holes_for(chosen)
    if not new:
        return "Нічого не відмічено."
    updates = []
    for p in _panels_of(chosen):
        added = new.get(id(p.group), [])
        if added:
            data = copy.deepcopy(p.data)
            data["holes"] = data["holes"] + added
            updates.append((p, data))
    err = update_panels(vp, updates, repaint=False)
    if err:
        return f"Кріплення не встановлено: {err}"
    n = sum(1 for c in chosen if not c.installed)
    text = f"Додано: {n}"
    _status(vp, text)
    return text


def _panels_of(chosen):
    seen = {}
    for c in chosen:
        for panel, _hole in c.holes:
            seen.setdefault(id(panel.group), panel)
    return list(seen.values())


def place_fastener(app, key, offset=None, step=None):
    """Встановити кріплення ``key`` в усі рекомендовані місця між виділеними
    панелями (для скриптів і тестів; у вікні місця обирає користувач)."""
    f = library.find(library.fasteners(), key)
    if f is None:
        return "Такого кріплення в бібліотеці немає."
    panels = selected_panels(app.viewport.scene)
    cands, skipped = fasteners.candidates(panels, f, offset, step)
    why = "".join(f"\n• {names}: {reason}" for names, reason in skipped)
    if not cands:
        return ("Стиків не знайдено: торець панелі має лежати на пласті іншої."
                if not skipped else f"{f['name']} не встановлено:{why}")
    return add_candidates(app, cands) + (f"\nПропущено:{why}" if skipped else "")


def remove_fasteners(app):
    """Прибрати кріплення з виділених панелей і парні отвори в сусідів."""
    vp = app.viewport
    panels = selected_panels(vp.scene)
    gone = {h.get("joint") for p in panels for h in p.data["holes"] if fasteners.is_fastener(h)}
    updates = []
    for p in all_panels(vp.scene):
        holes = [h for h in p.data["holes"] if h.get("joint") not in gone]
        if len(holes) != len(p.data["holes"]):
            data = copy.deepcopy(p.data)
            data["holes"] = holes
            updates.append((p, data))
    if not updates:
        return "На виділених панелях кріплення немає."
    err = update_panels(vp, updates, repaint=False)
    text = f"Кріплення не прибрано: {err}" if err else \
        f"Кріплення прибрано з {len(updates)} панел(ей)"
    _status(vp, text)
    return text


class _LibraryList(QWidget):
    """Спільне для панелей «Кріплення» і «Крайка»: список записів бібліотеки
    з описом обраного; оновлюється, коли бібліотеку змінили в налаштуваннях."""

    SETTING = ""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.lay = QVBoxLayout(self)
        self.head = QLabel(self)
        self.head.setWordWrap(True)
        self.lay.addWidget(self.head)
        self.list = QListWidget(self)
        self.lay.addWidget(self.list, 1)
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        self.lay.addWidget(self.details)
        self.list.currentRowChanged.connect(self._chosen)
        library.on_change(self.reload)

    def items(self):                            # pragma: no cover — перевизначають
        return []

    def describe(self, item):                   # pragma: no cover
        return ""

    def reload(self):
        keep = self.key() or str(QSettings().value(self.SETTING, ""))
        self.list.blockSignals(True)
        self.list.clear()
        for item in self.items():
            w = QListWidgetItem(item["name"], self.list)
            w.setData(Qt.UserRole, item["key"])
            w.setToolTip(self.describe(item))
            self.decorate(w, item)
        keys = [i["key"] for i in self.items()]
        self.list.setCurrentRow(keys.index(keep) if keep in keys else 0)
        self.list.blockSignals(False)
        self._chosen()

    def decorate(self, widget_item, item):
        pass

    def key(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def current(self):
        return library.find(self.items(), self.key())

    def _chosen(self, *_):
        item = self.current()
        self.details.setText(self.describe(item) if item else "")
        if item:
            QSettings().setValue(self.SETTING, item["key"])
        self.chosen(item)

    def chosen(self, item):
        pass


class FastenersPanel(_LibraryList):
    """Бічна панель «Кріплення».

    Обрали кріплення й виділили панелі — панель рахує рекомендовані місця
    (на відступі від країв стику, на довгих стиках ще й посередині з
    кроком) і показує їх у моделі пунктиром. Користувач відмічає потрібні —
    галочкою в списку або кліком у моделі (режим кріплення) — і натискає
    «Додати». Відступ і крок можна змінити тут же."""

    SETTING = "board_studio/fastener"
    PICK_PX = 12

    def __init__(self, app, activate=None):
        self.candidates, self.checked, self.skipped = [], set(), []
        self._boxes = holemarks.SceneBoxes()
        super().__init__(app)
        form = QFormLayout()
        self.offset = QDoubleSpinBox(self)
        self.step = QDoubleSpinBox(self)
        for box, hi in ((self.offset, 1000.0), (self.step, 5000.0)):
            box.setRange(0.0 if box is self.offset else 1.0, hi)
            box.setDecimals(1)
            box.setSuffix(" мм")
            box.valueChanged.connect(lambda _v: self.recompute())
        form.addRow("Відступ від краю", self.offset)
        form.addRow("Крок (найбільший)", self.step)
        self.lay.addLayout(form)
        self.lay.addWidget(QLabel("Рекомендовані місця:", self))
        self.places = QListWidget(self)
        self.places.itemChanged.connect(self._item_changed)
        self.lay.addWidget(self.places, 1)
        row = QHBoxLayout()
        self.all = QPushButton("Усі", self)
        self.none = QPushButton("Жодного", self)
        self.all.clicked.connect(lambda: self.set_checked(
            {c.key for c in self.candidates if not c.installed}))
        self.none.clicked.connect(lambda: self.set_checked(set()))
        row.addWidget(self.all)
        row.addWidget(self.none)
        self.lay.addLayout(row)
        row = QHBoxLayout()
        self.add = QPushButton("Додати", self)
        self.remove = QPushButton("Прибрати", self)
        self.add.clicked.connect(self.add_checked)
        self.remove.clicked.connect(self._remove)
        row.addWidget(self.add)
        row.addWidget(self.remove)
        self.lay.addLayout(row)
        if activate is not None:
            self.mode = QPushButton("Режим кріплення (клік по місцю — відмітити)", self)
            self.mode.clicked.connect(activate)
            self.lay.addWidget(self.mode)
        show = QGroupBox("Показувати кріплення в моделі", self)
        row = QHBoxLayout(show)
        self.show_always = QRadioButton("Постійно", show)
        self.show_in_mode = QRadioButton("Лише в режимі", show)
        self.show_in_mode.setToolTip("Отвори й рекомендовані місця видно, лише поки "
                                     "активний режим «Кріплення»")
        row.addWidget(self.show_always)
        row.addWidget(self.show_in_mode)
        row.addStretch(1)
        only = holemarks.show_when() == holemarks.IN_MODE
        (self.show_in_mode if only else self.show_always).setChecked(True)
        self.show_in_mode.toggled.connect(self._set_show)
        self.lay.addWidget(show)
        self.result = QLabel(self)
        self.result.setWordWrap(True)
        self.lay.addWidget(self.result)
        self.list.itemDoubleClicked.connect(lambda _i: self.set_checked(
            {c.key for c in self.candidates if not c.installed}))
        self.reload()
        self.refresh()

    def items(self):
        return library.fasteners()

    def describe(self, item):
        return fastener_summary(item)

    def chosen(self, item):
        if item is None or not hasattr(self, "offset"):
            return
        for box, key in ((self.offset, "offset"), (self.step, "step")):
            box.blockSignals(True)
            box.setValue(float(item.get(key) or 0.0))
            box.blockSignals(False)
        self.checked.clear()
        self.recompute()

    def _set_show(self, only_in_mode):
        holemarks.set_show_when(holemarks.IN_MODE if only_in_mode else holemarks.ALWAYS)
        vp = getattr(self.app, "viewport", None)
        if vp is not None:
            vp.update()

    # ---- рекомендації ----
    def _panels(self):
        vp = getattr(self.app, "viewport", None)
        if vp is None:
            return []
        try:
            return selected_panels(vp.scene)
        except Exception:                                   # noqa: BLE001 — панель не має падати
            return []

    def refresh(self):
        """Що виділено — оновлюється з кожною зміною документа й виділення."""
        panels = self._panels()
        n = len(panels)
        holes = sum(1 for p in panels for h in p.data["holes"] if fasteners.is_fastener(h))
        self.head.setText(
            f"Виділено панелей: {n}" + (f", отворів кріплення: {holes}" if holes else "")
            if n else "Виділіть панелі, між якими треба поставити кріплення.")
        self.remove.setEnabled(holes > 0)
        self.recompute(panels)

    def recompute(self, panels=None):
        if not hasattr(self, "places"):
            return
        panels = self._panels() if panels is None else panels
        f = self.current()
        if f is not None and len(panels) >= 2:
            self.candidates, self.skipped = fasteners.candidates(
                panels, f, self.offset.value(), self.step.value())
        else:
            self.candidates, self.skipped = [], []
        keys = {c.key for c in self.candidates if not c.installed}
        self.checked &= keys
        self.places.blockSignals(True)
        self.places.clear()
        for c in self.candidates:
            item = QListWidgetItem(c.label + (" — встановлено" if c.installed else ""),
                                   self.places)
            item.setData(Qt.UserRole, c.key)
            if c.installed:
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable & ~Qt.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if c.key in self.checked else Qt.Unchecked)
        self.places.blockSignals(False)
        if self.skipped:
            self.result.setText("Не стає:" + "".join(f"\n• {n}: {r}" for n, r in self.skipped))
        elif len(panels) >= 2 and not self.candidates:
            self.result.setText("Стиків не знайдено: торець панелі має лежати на пласті іншої.")
        self._buttons()

    def _buttons(self):
        free = [c for c in self.candidates if not c.installed]
        self.add.setEnabled(bool(self.checked))
        self.add.setText(f"Додати ({len(self.checked)})" if self.checked else "Додати")
        self.all.setEnabled(bool(free))
        self.none.setEnabled(bool(self.checked))
        vp = getattr(self.app, "viewport", None)
        if vp is not None:
            vp.update()

    def _item_changed(self, item):
        key = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.checked.add(key)
        else:
            self.checked.discard(key)
        self._buttons()

    def set_checked(self, keys):
        self.checked = set(keys)
        self.places.blockSignals(True)
        for i in range(self.places.count()):
            item = self.places.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in self.checked
                                   else Qt.Unchecked)
        self.places.blockSignals(False)
        self._buttons()

    def toggle(self, key):
        c = next((c for c in self.candidates if c.key == key), None)
        if c is None or c.installed:
            return
        self.set_checked(self.checked ^ {key})

    def add_checked(self):
        chosen = [c for c in self.candidates if c.key in self.checked]
        self.result.setText(add_candidates(self.app, chosen))
        self.checked.clear()
        self.refresh()

    def _remove(self):
        self.result.setText(remove_fasteners(self.app))
        self.refresh()

    # ---- модель: накладка і вибір кліком ----
    def _pixels(self, viewport):
        if not self.candidates:
            return None
        pts = []
        for c in self.candidates:
            depth = next((h["depth"] or 20.0 for h in c.f["holes"] if h["where"] == "edge"), 20.0)
            pts.append(c.point)
            pts.append(c.point + c.inward * (depth / 1000))
        return viewport.world_to_pixels(np.array(pts, dtype=np.float64))

    def pick(self, viewport, x, y):
        """Ключ рекомендованого місця біля пікселя (x, y) або ``None``."""
        if not self.isVisible():
            return None
        px = self._pixels(viewport)
        if px is None:
            return None
        xs, ys, front = px
        best, dist = None, self.PICK_PX
        for i, c in enumerate(self.candidates):
            if not front[2 * i]:
                continue
            d = math.hypot(float(xs[2 * i]) - x, float(ys[2 * i]) - y)
            if d <= dist:
                best, dist = c.key, d
        return best

    def _covered(self, viewport):
        """Для кожного місця: чи закриває його стороння панель."""
        self._boxes.update(viewport.scene)
        pts = np.array([c.point for c in self.candidates], dtype=np.float64).reshape(-1, 3)
        boxes = self._boxes.boxes
        status = boxes.status(holemarks.view_of(viewport), pts[:, None], boxes.touch(pts))
        return status[:, 0] == holemarks.HIDDEN

    def draw(self, viewport, painter):
        if not self.isVisible() or not self.candidates or not holemarks.shown_in(viewport):
            return
        xs, ys, front = self._pixels(viewport)
        covered = self._covered(viewport)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        for i, c in enumerate(self.candidates):
            if not (front[2 * i] and front[2 * i + 1]) or c.installed and covered[i]:
                continue
            p, q = QPointF(float(xs[2 * i]), float(ys[2 * i])), \
                QPointF(float(xs[2 * i + 1]), float(ys[2 * i + 1]))
            if c.installed:
                pen, brush = QPen(self.INSTALLED, 2), Qt.NoBrush
            elif c.key in self.checked:
                pen, brush = QPen(self.CHECKED, 2.5), QColor(self.CHECKED.red(),
                                                            self.CHECKED.green(),
                                                            self.CHECKED.blue(), 110)
            else:
                pen, brush = QPen(self.FREE, 2, Qt.DashLine), Qt.NoBrush
            painter.setPen(pen)
            painter.setBrush(brush)
            painter.drawLine(p, q)                  # вісь отвору в торці
            painter.drawEllipse(p, 7.0, 7.0)

    FREE = QColor(40, 110, 220)
    CHECKED = QColor(235, 120, 20)
    INSTALLED = QColor(40, 160, 70)


class EdgeBandPanel(_LibraryList):
    """Бічна панель «Крайка»: обрати крайку з бібліотеки; режим крайки —
    клік по торцю додає її, ще клік прибирає."""

    SETTING = "board_studio/edge_band"

    def __init__(self, app, tool, activate):
        self.tool = tool
        super().__init__(app)
        self.head.setText("Клік по торцю панелі — додати обрану крайку, ще клік — прибрати. "
                          "Встановлені крайки підсвічено їхнім кольором.")
        self.mode = QPushButton("Режим крайки", self)
        self.mode.clicked.connect(activate)
        self.lay.addWidget(self.mode)
        self.reload()

    def items(self):
        return library.edges()

    def describe(self, item):
        art = f", артикул {item['article']}" if item.get("article") else ""
        return f"Товщина {item['thickness']:g} мм{art}"

    def decorate(self, widget_item, item):
        from PySide6.QtGui import QIcon, QPixmap
        pix = QPixmap(16, 16)
        pix.fill(QColor(item.get("color") or "#999999"))
        widget_item.setIcon(QIcon(pix))

    def chosen(self, item):
        self.tool.band = item
        vp = getattr(self.app, "viewport", None)
        if vp is not None:
            vp.update()


def show_panel(app, attr, title, name, make):
    """Відкрити бічну панель (створюється раз)."""
    panel = getattr(app, attr, None)
    if panel is None:
        panel = make()
        setattr(app, attr, panel)
        setattr(app, attr + "_dock", app.add_panel(title, panel, name=name))
        if hasattr(panel, "refresh"):
            app.on_document_changed(panel.refresh)
    if hasattr(panel, "refresh"):
        panel.refresh()
    app.show_panel(getattr(app, attr + "_dock"))
    return panel


def show_fasteners(app, activate=None):
    """Пункт меню «Кріплення»: бічна панель (і накладка з рекомендаціями)."""
    first = getattr(app, "_fasteners_panel", None) is None
    panel = show_panel(app, "_fasteners_panel", "Кріплення", "fasteners",
                       lambda: FastenersPanel(app, activate))
    if first:
        app.add_overlay(panel.draw)
    return panel


# ---- Експорт DXF -------------------------------------------------------------------------

def export_dxf(app, path=None):
    """Виділені панелі (або всі видимі, якщо їх не виділено) → DXF для
    ViyarPro. ``path`` — без діалогу (для тестів і скриптів)."""
    vp = app.viewport
    panels = selected_panels(vp.scene) or all_panels(vp.scene)
    if not panels:
        QMessageBox.information(app.window, "Board Studio",
                                "There are no Board Studio panels to export.")
        return None
    if path is None:
        current = getattr(app.window, "_current_path", None)
        stem = Path(current).stem if current else "untitled"
        start = str(Path(current).parent / f"{stem} flatten.dxf") if current \
            else str(Path.home() / f"{stem} flatten.dxf")
        path, _f = QFileDialog.getSaveFileName(app.window, "Export DXF for ViyarPro", start,
                                               "DXF (*.dxf)")
        if not path:
            return None
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
    try:
        export([p.dxf_part() for p in panels], path)
        lost = [p.name for p in panels if p.cutouts or not p.outline()]
        off = [f"{p.name} ({n})" for p in panels if (n := fasteners.misplaced(p))]
    except OSError as exc:
        QMessageBox.warning(app.window, "Board Studio", f"Export error: {exc}")
        return None
    warn = []
    if lost:
        warn.append("Експортовано, але форму передано не повністю (внутрішні вирізи чи "
                    "нерозпізнаний контур): " + ", ".join(lost))
    if off:
        warn.append("Отвори за контуром панелі — приберіть кріплення й поставте знову: "
                    + ", ".join(off))
    if warn:
        QMessageBox.warning(app.window, "Board Studio", "\n\n".join(warn))
    _status(vp, f"{len(panels)} panel(s) exported to {path}", 6000)
    return path
