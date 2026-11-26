# SPDX-License-Identifier: GPL-3.0-or-later
"""Board Studio для IngeTrazo — параметричні панелі за 3 точками (порт
SketchUp-розширення). Extensions ▸ Board Studio і тулбар «Panel Creator»:

- **New 3-Point Panel** — діалог параметрів, потім малювання;
- **Next 3-Point Panel** — одразу малювання з попередніми параметрами;
- **Panel Properties** — напрямок текстури, декор Viyar;
- **Fasteners** — бічна панель: кріплення з бібліотеки в стики «торець на пласть»;
- **Edge Banding** — бічна панель і режим: клік по торцю додає/прибирає крайку;
- **Settings** — бібліотека кріплень (присадки, зазори, обмеження) і крайок;
- **Export DXF for ViyarPro** — розкрій у форматі ABF_Flatten.

Назви пунктів — англійські ключі; мову інтерфейсу дає :mod:`.i18n`.
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
from .i18n import N_, tr
from .settings import edit_settings
from .materials import DEFAULT, PRESETS, label, preset_thickness
from .panels import panel_data
from .tool import ThreePointPanelTool

ICONS = Path(__file__).parent / "icons"
#: (атрибут інструмента, підпис, типове значення в мм, мінімум)
FIELDS = (("thickness", N_("Thickness (mm)"), 16.0, 0.01),
          ("offset_length", N_("Offset along Length (mm)"), 0.0, 0.0),
          ("offset_width", N_("Offset along Width/Height (mm)"), 0.0, 0.0))


def setup(app):
    tool = ThreePointPanelTool()
    _load(tool)
    key = f"plugin_{app.key}_ThreePointPanelTool"
    HINTS.setdefault(key, {
        "idle": tr("Click first corner."),
        "started": tr("Click the next point, or type a length and press Enter. "
                      "Ctrl = flip push direction."),
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
    HINTS.setdefault(band_key, {"idle": tr("Click an edge of a panel to add the edge band; "
                                           "click again to remove it.")})

    fasten_tool = FastenerTool(lambda: getattr(app, "_fasteners_panel", None))
    fasten_key = f"plugin_{app.key}_FastenerTool"
    HINTS.setdefault(fasten_key, {"idle": tr("Click a suggested place to mark it; "
                                             "click a panel to select it.")})

    def fasten_mode():
        """Пункт «Кріплення»: панель з рекомендаціями + режим кріплення."""
        ui.show_fasteners(app, lambda: activate(fasten_tool, fasten_key))
        activate(fasten_tool, fasten_key)

    def edge_mode():
        """Пункт «Крайка»: панель з крайками + режим крайки."""
        ui.show_panel(app, "_edges_panel", tr("Edge Banding"), "edges",
                      lambda: ui.EdgeBandPanel(app, band_tool,
                                               lambda: activate(band_tool, band_key)))
        activate(band_tool, band_key)

    actions = []
    for text, tip, icon, dialog in (
            (tr("New 3-Point Panel"), tr("Create new panel by 3 points with parameters dialog"),
             "new.png", True),
            (tr("Next 3-Point Panel"), tr("Create next panel by 3 points using previous "
                                          "settings without dialog"), "next.png", False)):
        act = QAction(QIcon(str(ICONS / icon)), text, app.window)
        act.setToolTip(f"{text}\n{tip}")
        act.setStatusTip(tip)
        act.triggered.connect(lambda _c=False, d=dialog: run(d))
        actions.append(act)

    commands = []
    for text, tip, icon, fn in (
            (tr("Panel Properties…"),
             tr("Texture direction and Viyar decor of the selected panels"),
             "properties.png", ui.edit_properties),
            (tr("Fasteners"), tr("Suggested fastener places between the selected panels: "
                                 "mark the ones you need and add them"), "dowels.png", lambda _app: fasten_mode()),
            (tr("Edge Banding"), tr("Edge banding mode: click an edge of a panel to add the "
                                    "chosen band, click again to remove it"), "edgeband.png", lambda _app: edge_mode()),
            (tr("Export DXF for ViyarPro…"), tr("Export the selected panels (or all panels) "
                                                "to DXF for ViyarPro"), "dxf.png", ui.export_dxf)):
        act = QAction(QIcon(str(ICONS / icon)) if icon else QIcon(), text, app.window)
        act.setToolTip(f"{text.rstrip('…')}\n{tip}")
        act.setStatusTip(tip)
        act.triggered.connect(lambda _c=False, f=fn: f(app))
        commands.append(act)
    overlay = HoleOverlay(app)
    show = QAction(tr("Show Holes"), app.window, checkable=True, checked=True)
    show.setStatusTip(tr("Show dowel and drilling marks on panels"))
    show.toggled.connect(lambda on: (setattr(overlay, "visible", on), app.viewport.update()))

    settings = QAction(tr("Settings…"), app.window)
    settings.setStatusTip(tr("Board Studio library of fasteners and edge bands"))
    settings.triggered.connect(lambda _c=False: edit_settings(app))

    menu = app.add_menu("Board Studio")
    if menu is not None:
        menu.addActions(actions)
        menu.addSeparator()
        menu.addActions(commands)
        menu.addSeparator()
        menu.addAction(show)
        menu.addAction(settings)
    bar = QToolBar(tr("Panel Creator"), app.window)
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
    dlg.setWindowTitle(tr("Create Panel Parameters"))
    form = QFormLayout(dlg)
    combo = QComboBox(dlg)
    for name, *_ in PRESETS:
        combo.addItem(label(name), name)
    combo.setCurrentIndex(combo.findData(tool.material))
    form.addRow(tr("Material"), combo)
    spins = {}
    for name, text, _default, minimum in FIELDS:
        box = spins[name] = QDoubleSpinBox(dlg)
        box.setRange(minimum, 100000.0)
        box.setSuffix(f" {tr('mm')}")
        box.setValue(getattr(tool, name) * 1000)
        form.addRow(tr(text), box)
    # Плита підставляє свою товщину; її можна виправити вручну.
    combo.currentIndexChanged.connect(
        lambda _i: spins["thickness"].setValue(preset_thickness(combo.currentData())))
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    form.addRow(buttons)
    spins["thickness"].selectAll()
    if dlg.exec() != QDialog.Accepted:
        return False
    qs = QSettings()
    tool.material = combo.currentData()
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
    props = [(tr("Material"), label(data["material"]) if data.get("material") else "—")]
    props += [(text, fmt_len_fine(data[k])) for k, text in (
        ("length", tr("Length")), ("width", tr("Width")), ("thickness", tr("Thickness")))
        if k in data]
    if data["article"]:
        props.append((tr("Decor"), f"${data['article']} {data['decor']}".strip()))
    props.append((tr("Texture"), tr(dict(ui.GRAIN_LABELS).get(data["grain"], data["grain"]))))
    props.append((tr("Edge banding"), " / ".join(
        (b or {}).get("name") or (f"{e:g}" if e else "—")
        for b, e in zip(data["bands"], data["edges"]))))
    extra = [(b.get("band") or {}).get("name") or "—" for b in data["extra_bands"]]
    if extra:
        props.append((tr("Edge banding (curved)"), " / ".join(extra)))
    holes = data["holes"]
    if holes:
        props.append((tr("Holes"), str(len(holes))))
    return {"type": tr("Panel"), "props": props}
