# SPDX-License-Identifier: GPL-3.0-or-later
"""Вікно «Налаштування Board Studio»: бібліотека кріплень і крайок.

Кріплення: назва, правила розстановки (відступ від кінців стику, крок,
найменша довжина стику), обмеження (товщини деталей, товщина стінки біля
отвору) і таблиця присадок. Крайка: назва, товщина, колір, артикул.
Зберігається кнопкою OK (див. :mod:`.library`).
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QTableWidget, QTabWidget,
                               QVBoxLayout, QWidget)

from . import library

HOLE_COLUMNS = ("Де", "Ø, мм", "Глибина, мм (0 — наскрізь)", "Зсув до середини, мм",
                "Від торця, мм", "Артикул", "Група ABF", "Шар DXF (необов'язково)")


def _spin(parent, lo, hi, decimals=1, suffix=" мм"):
    box = QDoubleSpinBox(parent)
    box.setRange(lo, hi)
    box.setDecimals(decimals)
    box.setSuffix(suffix)
    return box


class _Editor(QWidget):
    """Список записів зліва (додати / дублювати / видалити) і форма справа."""

    def __init__(self, items, template):
        super().__init__()
        self.items = items
        self.template = template
        self._current = None
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget(self)
        self.list.setMinimumWidth(180)
        left.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in (("Додати", self.add), ("Дублювати", self.duplicate),
                         ("Видалити", self.delete)):
            btn = QPushButton(text, self)
            btn.setAutoDefault(False)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        left.addLayout(row)
        lay.addLayout(left)
        self.form_box = QWidget(self)
        lay.addWidget(self.form_box, 1)
        self.build_form(self.form_box)
        self.list.currentRowChanged.connect(self._select)
        self._fill_list()

    # ---- список ----
    def _fill_list(self, row=0):
        self.list.blockSignals(True)
        self.list.clear()
        for item in self.items:
            w = QListWidgetItem(item["name"], self.list)
            self.decorate(w, item)
        self.list.blockSignals(False)
        self._current = None
        if self.items:
            self.list.setCurrentRow(min(row, len(self.items) - 1))
        self.form_box.setEnabled(bool(self.items))

    def decorate(self, w, item):
        pass

    def _select(self, row):
        self.commit()
        self._current = self.items[row] if 0 <= row < len(self.items) else None
        if self._current is not None:
            self.load(self._current)

    def add(self):
        self.commit()
        item = copy.deepcopy(self.template)
        item["name"] = "Нове"
        item["key"] = library.new_key(self.items, "item")
        self.items.append(item)
        self._fill_list(len(self.items) - 1)

    def duplicate(self):
        self.commit()
        if self._current is None:
            return
        item = copy.deepcopy(self._current)
        item["name"] += " (копія)"
        item["key"] = library.new_key(self.items, item["key"])
        self.items.append(item)
        self._fill_list(len(self.items) - 1)

    def delete(self):
        row = self.list.currentRow()
        if 0 <= row < len(self.items):
            self._current = None
            del self.items[row]
            self._fill_list(row)

    def commit(self):
        """Записати форму в поточний запис."""
        if self._current is not None:
            self.store(self._current)
            row = self.items.index(self._current)
            w = self.list.item(row)
            if w is not None:
                w.setText(self._current["name"])
                self.decorate(w, self._current)


class FastenerEditor(_Editor):
    def build_form(self, box):
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QFormLayout()
        self.name = QLineEdit(box)
        top.addRow("Назва", self.name)
        lay.addLayout(top)
        self.spins = {}
        for title, keys in (("Розстановка", ("offset", "step", "min_step", "min_joint")),
                            ("Обмеження", ("min_edge_thickness", "min_face_thickness",
                                           "min_wall"))):
            group = QGroupBox(title, box)
            form = QFormLayout(group)
            for key, label, lo, hi in library.FASTENER_FIELDS:
                if key in keys:
                    self.spins[key] = _spin(group, lo, hi)
                    form.addRow(label, self.spins[key])
            lay.addWidget(group)
        holes = QGroupBox("Присадки (отвори відносно точки кріплення на стику)", box)
        hl = QVBoxLayout(holes)
        self.table = QTableWidget(0, len(HOLE_COLUMNS), holes)
        self.table.setHorizontalHeaderLabels(HOLE_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        hl.addWidget(self.table)
        row = QHBoxLayout()
        for text, fn in (("Додати отвір", lambda: self._add_row(library.hole("edge", 8.0, 12.0))),
                         ("Видалити отвір", self._del_row)):
            btn = QPushButton(text, holes)
            btn.setAutoDefault(False)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        row.addStretch(1)
        hl.addLayout(row)
        lay.addWidget(holes, 1)

    def _add_row(self, h):
        r = self.table.rowCount()
        self.table.insertRow(r)
        where = QComboBox(self.table)
        for key, label in library.WHERE:
            where.addItem(label, key)
        where.setCurrentIndex(max(0, where.findData(h["where"])))
        self.table.setCellWidget(r, 0, where)
        for col, key, lo, hi in ((1, "d", 0.5, 100.0), (2, "depth", 0.0, 500.0),
                                 (3, "along", -1000.0, 1000.0), (4, "from_edge", 0.0, 1000.0)):
            box = _spin(self.table, lo, hi, suffix="")
            value = h.get(key)
            box.setValue(0.0 if value is None else float(value))
            self.table.setCellWidget(r, col, box)
        for col, key in ((5, "article"), (6, "group"), (7, "layer")):
            edit = QLineEdit(str(h.get(key) or ""), self.table)
            if key == "group":
                edit.setPlaceholderText(library.DEFAULT_GROUP.get(h["where"], ""))
            self.table.setCellWidget(r, col, edit)

    def _del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def load(self, f):
        self.name.setText(f["name"])
        for key, box in self.spins.items():
            box.setValue(float(f.get(key) or 0.0))
        self.table.setRowCount(0)
        for h in f["holes"]:
            self._add_row(h)

    def store(self, f):
        f["name"] = self.name.text().strip() or "Без назви"
        for key, box in self.spins.items():
            f[key] = box.value()
        holes = []
        for r in range(self.table.rowCount()):
            cell = self.table.cellWidget
            where = cell(r, 0).currentData()
            depth = cell(r, 2).value()
            article = cell(r, 5).text().strip().lstrip("$")
            holes.append({"where": where, "d": cell(r, 1).value(),
                          "depth": None if depth == 0 else depth,
                          "along": cell(r, 3).value(), "from_edge": cell(r, 4).value(),
                          "article": article,
                          "group": cell(r, 6).text().strip() or library.DEFAULT_GROUP[where],
                          "layer": cell(r, 7).text().strip()})
        f["holes"] = holes


class EdgeEditor(_Editor):
    def build_form(self, box):
        form = QFormLayout(box)
        form.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit(box)
        self.thickness = _spin(box, 0.0, 10.0, decimals=2)
        self.article = QLineEdit(box)
        self.color = QPushButton(box)
        self.color.setAutoDefault(False)
        self.color.clicked.connect(self._pick_color)
        self._color = "#999999"
        form.addRow("Назва", self.name)
        form.addRow("Товщина", self.thickness)
        form.addRow("Колір (підсвітка)", self.color)
        form.addRow("Артикул", self.article)

    def decorate(self, w, item):
        pix = QPixmap(16, 16)
        pix.fill(QColor(item.get("color") or "#999999"))
        w.setIcon(QIcon(pix))

    def _show_color(self):
        pix = QPixmap(40, 16)
        pix.fill(QColor(self._color))
        self.color.setIcon(QIcon(pix))
        self.color.setText(self._color)

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Колір крайки")
        if c.isValid():
            self._color = c.name()
            self._show_color()

    def load(self, e):
        self.name.setText(e["name"])
        self.thickness.setValue(float(e.get("thickness") or 0.0))
        self.article.setText(e.get("article") or "")
        self._color = e.get("color") or "#999999"
        self._show_color()

    def store(self, e):
        e["name"] = self.name.text().strip() or "Без назви"
        e["thickness"] = self.thickness.value()
        e["article"] = self.article.text().strip()
        e["color"] = self._color


class SettingsDialog(QDialog):
    def __init__(self, parent=None, data=None):
        super().__init__(parent)
        self.setWindowTitle("Налаштування Board Studio")
        self.resize(980, 620)
        self.data = copy.deepcopy(data or library.load())
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.fasteners = FastenerEditor(self.data["fasteners"], library.DEFAULT_FASTENERS[0])
        self.edges = EdgeEditor(self.data["edges"], library.DEFAULT_EDGES[0])
        self.tabs.addTab(self.fasteners, "Кріплення")
        self.tabs.addTab(self.edges, "Крайка")
        lay.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel
                                   | QDialogButtonBox.RestoreDefaults, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).setText("Типові")
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        lay.addWidget(buttons)

    def _defaults(self):
        self.data["fasteners"][:] = copy.deepcopy(library.DEFAULT_FASTENERS)
        self.data["edges"][:] = copy.deepcopy(library.DEFAULT_EDGES)
        for editor in (self.fasteners, self.edges):
            editor._current = None
            editor._fill_list()

    def result_data(self):
        self.fasteners.commit()
        self.edges.commit()
        return self.data


def edit_settings(app):
    dlg = SettingsDialog(app.window)
    dlg.setAttribute(Qt.WA_DeleteOnClose, False)
    if dlg.exec() == QDialog.Accepted:
        library.save(dlg.result_data())
