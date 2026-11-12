# SPDX-License-Identifier: GPL-3.0-or-later
"""Board Studio для IngeTrazo — параметричні панелі за 3 точками (порт
SketchUp-розширення). Extensions ▸ Board Studio і тулбар «Panel Creator»:

- **New 3-Point Panel** — діалог параметрів, потім малювання;
- **Next 3-Point Panel** — одразу малювання з попередніми параметрами.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QToolBar)

from core.units import fmt_len_fine
from views.status_hints import HINTS

from .materials import DEFAULT, PRESETS, preset_thickness
from .tool import EXT_KEY, ThreePointPanelTool

ICONS = Path(__file__).parent / "icons"
#: (атрибут інструмента, підпис, типове значення в мм, мінімум)
FIELDS = (("thickness", "Thickness (mm)", 16.0, 0.01),
          ("offset_length", "Offset along Length (mm)", 0.0, 0.0),
          ("offset_width", "Offset along Width/Height (mm)", 0.0, 0.0))


def setup(app):
    tool = ThreePointPanelTool()
    _load(tool)
    key = f"plugin_{app.key}_ThreePointPanelTool"
    HINTS.setdefault(key, {
        "idle": "Click first corner.",
        "started": "Click the next point, or type a length and press Enter. "
                   "Ctrl = flip push direction.",
    })

    def run(dialog):
        if dialog and not _ask(app.window, tool):
            return
        win = app.window
        if hasattr(win, "_activate_tool"):      # як вбудований: назва, підказка, VCB, Repeat
            win._tools[key] = tool
            win._activate_tool(key)
        else:
            app.viewport.set_active_tool(tool)
        app.viewport.setFocus()

    actions = []
    for text, tip, icon, dialog in (
            ("New 3-Point Panel", "Create new panel by 3 points with parameters dialog",
             "new.png", True),
            ("Next 3-Point Panel", "Create next panel by 3 points using previous settings "
             "without dialog", "next.png", False)):
        act = QAction(QIcon(str(ICONS / icon)), text, app.window)
        act.setToolTip(f"{text}\n{tip}")
        act.setStatusTip(tip)
        act.triggered.connect(lambda _c=False, d=dialog: run(d))
        actions.append(act)

    menu = app.add_menu("Board Studio")
    if menu is not None:
        menu.addActions(actions)
    bar = QToolBar("Panel Creator", app.window)
    bar.setObjectName("extension_board_studio_toolbar")    # стабільне: макет вікна
    bar.addActions(actions)
    app.window.addToolBar(Qt.TopToolBarArea, bar)
    app.add_outliner_kind(_outliner_kind)


def _load(tool):
    """Останні параметри (між сесіями — у QSettings, у мм)."""
    qs = QSettings()
    material = str(qs.value("board_studio/material", DEFAULT))
    tool.material = material if any(material == p[0] for p in PRESETS) else DEFAULT
    for name, _label, default, _min in FIELDS:
        try:
            mm = float(qs.value(f"board_studio/{name}_mm", default))
        except (TypeError, ValueError):
            mm = default
        setattr(tool, name, mm / 1000)


def _ask(parent, tool):
    """Діалог параметрів (аналог ``UI.inputbox``); True — прийнято й збережено."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Create Panel Parameters")
    form = QFormLayout(dlg)
    combo = QComboBox(dlg)
    combo.addItems([name for name, *_ in PRESETS])
    combo.setCurrentText(tool.material)
    form.addRow("Material", combo)
    spins = {}
    for name, label, _default, minimum in FIELDS:
        box = spins[name] = QDoubleSpinBox(dlg)
        box.setRange(minimum, 100000.0)
        box.setSuffix(" mm")
        box.setValue(getattr(tool, name) * 1000)
        form.addRow(label, box)
    # Плита підставляє свою товщину; її можна виправити вручну.
    combo.currentTextChanged.connect(lambda name: spins["thickness"].setValue(preset_thickness(name)))
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    form.addRow(buttons)
    spins["thickness"].selectAll()
    if dlg.exec() != QDialog.Accepted:
        return False
    qs = QSettings()
    tool.material = combo.currentText()
    qs.setValue("board_studio/material", tool.material)
    for name, box in spins.items():
        setattr(tool, name, box.value() / 1000)
        qs.setValue(f"board_studio/{name}_mm", box.value())
    return True


def _outliner_kind(group):
    """Browser: тип «Panel» і розміри."""
    data = (getattr(group, "ext", None) or {}).get(EXT_KEY)
    if not data:
        return None
    return {"type": "Panel",
            "props": [("Material", data.get("material", "—"))]
                     + [(k.capitalize(), fmt_len_fine(data[k])) for k in ("length", "width", "thickness")]}
