# SPDX-License-Identifier: GPL-3.0-or-later
"""Board Studio для IngeTrazo — параметричні панелі за 3 точками (порт
SketchUp-розширення). Extensions ▸ Board Studio і тулбар «Panel Creator»:

- **New 3-Point Panel** — діалог параметрів, потім малювання;
- **Next 3-Point Panel** — одразу малювання з попередніми параметрами;
- **Panel Properties** — напрямок текстури, декор Viyar;
- **Кріплення** — бічна панель: кріплення з бібліотеки в стики «торець на пласть»;
- **Крайка** — бічна панель і режим: клік по торцю додає/прибирає крайку;
- **Налаштування** — бібліотека кріплень (присадки, зазори, обмеження) і крайок;
- **Export DXF for ViyarPro** — розкрій у форматі ABF_Flatten.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QToolBar)

from core.units import fmt_len_fine
from views.status_hints import HINTS

from . import ui
from .edgeband import EdgeBandTool
from .fastenmode import FastenerTool
from .holemarks import HoleOverlay
from .settings import edit_settings
from .materials import DEFAULT, PRESETS, preset_thickness
from .panels import panel_data
from .tool import ThreePointPanelTool

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

    def activate(t, k):
        win = app.window
        if hasattr(win, "_activate_tool"):      # як вбудований: назва, підказка, VCB, Repeat
            win._tools[k] = t
            win._activate_tool(k)
        else:
            app.viewport.set_active_tool(t)
        app.viewport.setFocus()

    def run(dialog):
        if dialog and not _ask(app.window, tool):
            return
        activate(tool, key)

    band_tool = EdgeBandTool()
    band_key = f"plugin_{app.key}_EdgeBandTool"
    HINTS.setdefault(band_key, {"idle": "Click an edge of a panel to add the edge band; "
                                        "click again to remove it."})

    fasten_tool = FastenerTool(lambda: getattr(app, "_fasteners_panel", None))
    fasten_key = f"plugin_{app.key}_FastenerTool"
    HINTS.setdefault(fasten_key, {"idle": "Click a suggested place to mark it; "
                                          "click a panel to select it."})

    def fasten_mode():
        """Пункт «Кріплення»: панель з рекомендаціями + режим кріплення."""
        ui.show_fasteners(app, lambda: activate(fasten_tool, fasten_key))
        activate(fasten_tool, fasten_key)

    def edge_mode():
        """Пункт «Крайка»: панель з крайками + режим крайки."""
        ui.show_panel(app, "_edges_panel", "Крайка", "edges",
                      lambda: ui.EdgeBandPanel(app, band_tool,
                                               lambda: activate(band_tool, band_key)))
        activate(band_tool, band_key)

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

    commands = []
    for text, tip, icon, fn in (
            ("Panel Properties…", "Texture direction and Viyar decor of the selected panels",
             "properties.png", ui.edit_properties),
            ("Кріплення", "Кріплення: рекомендовані місця між виділеними панелями — "
             "відмітити потрібні й додати", "dowels.png", lambda _app: fasten_mode()),
            ("Крайка", "Режим крайки: клік по торцю панелі додає обрану крайку, "
             "ще клік — прибирає", "edgeband.png", lambda _app: edge_mode()),
            ("Export DXF for ViyarPro…", "Export the selected panels (or all panels) "
             "to DXF for ViyarPro", "dxf.png", ui.export_dxf)):
        act = QAction(QIcon(str(ICONS / icon)) if icon else QIcon(), text, app.window)
        act.setToolTip(f"{text.rstrip('…')}\n{tip}")
        act.setStatusTip(tip)
        act.triggered.connect(lambda _c=False, f=fn: f(app))
        commands.append(act)
    overlay = HoleOverlay(app)
    show = QAction("Show Holes", app.window, checkable=True, checked=True)
    show.setStatusTip("Show dowel and drilling marks on panels")
    show.toggled.connect(lambda on: (setattr(overlay, "visible", on), app.viewport.update()))

    settings = QAction("Налаштування…", app.window)
    settings.setStatusTip("Бібліотека кріплень і крайок Board Studio")
    settings.triggered.connect(lambda _c=False: edit_settings(app))

    menu = app.add_menu("Board Studio")
    if menu is not None:
        menu.addActions(actions)
        menu.addSeparator()
        menu.addActions(commands)
        menu.addSeparator()
        menu.addAction(show)
        menu.addAction(settings)
    bar = QToolBar("Panel Creator", app.window)
    bar.setObjectName("extension_board_studio_toolbar")    # стабільне: макет вікна
    bar.addActions(actions)
    bar.addSeparator()
    bar.addActions([a for a in commands if not a.icon().isNull()])
    app.window.addToolBar(Qt.TopToolBarArea, bar)
    app.add_outliner_kind(_outliner_kind)
    app.add_overlay(overlay)
    app.add_context_menu(lambda menu, selection: _context_menu(app, menu, selection, commands))


def _context_menu(app, menu, selection, commands):
    """Правий клік по панелі: ті самі команди (діалоги — після закриття меню)."""
    from PySide6.QtCore import QTimer
    from core.group import Group
    if not any(isinstance(g, Group) and (panel_data(g) or g.children) for g in selection):
        return
    for act in commands:
        entry = menu.addAction(act.text())
        entry.triggered.connect(lambda _c=False, a=act: QTimer.singleShot(0, a.trigger))


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
    """Browser: тип «Panel», розміри, декор, текстура, кромка, шканти."""
    data = panel_data(group)
    if not data:
        return None
    props = [("Material", data.get("material", "—"))]
    props += [(k.capitalize(), fmt_len_fine(data[k])) for k in ("length", "width", "thickness")
              if k in data]
    if data["article"]:
        props.append(("Decor", f"${data['article']} {data['decor']}".strip()))
    props.append(("Texture", dict(ui.GRAIN_LABELS).get(data["grain"], data["grain"])))
    props.append(("Edge banding", " / ".join(
        (b or {}).get("name") or (f"{e:g}" if e else "—")
        for b, e in zip(data["bands"], data["edges"]))))
    extra = [(b.get("band") or {}).get("name") or "—" for b in data["extra_bands"]]
    if extra:
        props.append(("Edge banding (curved)", " / ".join(extra)))
    holes = data["holes"]
    if holes:
        props.append(("Holes", str(len(holes))))
    return {"type": "Panel", "props": props}
