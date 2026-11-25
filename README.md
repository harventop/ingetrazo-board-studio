# Board Studio

An IngeTrazo extension for creating parametric furniture and cabinetry panels by defining 3 points in 3D space. A Python port of the Board Studio extension for SketchUp.

## Features

- **3-Point Creation**: Define panel origin, length/width direction, and height with 3 clicks or by typing values (Measurements box + Enter).
- **Board Materials**: Choose the board type from a list (Chipboard / ДСП 10–38 mm, MDF / МДФ 6–22 mm, Hardboard / ДВП 3–4 mm). The board sets its nominal thickness, which you can still adjust in mm.
- **Parametric Settings**: Set panel thickness (mm), offset along length (mm), and offset along width/height (mm).
- **Automatic Textures**:
  - Faces get an oak laminate texture with the grain running along the panel length (from the 1st to the 2nd point).
  - Edges get a chipboard texture (ДСП) or a fibreboard texture (МДФ / ДВП), depending on the board.
  - The materials appear in the document's materials panel. Textures are embedded in the `.igz` file and follow the panel when you move, rotate or scale it.
- **Two Workflow Commands**:
  - **New 3-Point Panel**: Opens the parameters dialog to choose the board and dimensions before drawing.
  - **Next 3-Point Panel**: Skips the dialog and instantly draws using the previous settings (remembered between sessions).
- **Live 3D Preview**: Real-time textured preview of the panel volume. When offsets are set, the original boundary is shown dashed.
- **Flip Extrusion**: Toggle extrusion direction dynamically using `Ctrl`.
- **Clean Geometry**: Automatically generates an isolated group ("Panel N") with a closed solid and correct face normals. Undo removes it in one step. If a group is open for editing, the panel is created inside it.
- **Browser Integration**: Panels are listed with type "Panel", their material, dimensions, decor, texture direction, edge banding and number of holes.
- **Panel Properties**: texture direction (along the length, along the width, or no texture — plain decor) and the Viyar decor (article and name, used for the material in the DXF export), for one or many selected panels. A field where the panels differ shows `(keep)` and leaves each panel's own value.
- **Edge banding (Крайка)**: the **Крайка** command opens a side panel with the edge bands from the library and enters edge-banding mode. Click an edge of a panel to add the chosen band, click it again to remove it (a click with another band replaces it). While the mode is on, every band already applied is highlighted in its colour, and the edge under the cursor shows what a click will do. Each click is one undo step. Banded edges are painted with the decor, the others show the board core; the band thickness insets the cut contour in the DXF.
- **Fasteners (Кріплення)**: the **Кріплення** command opens a side panel, like Entity Info, with the fasteners from the library, and enters fastener mode. Select the panels and pick a fastener: wherever the edge of one panel lies flat on the face of another, the suggested places are drawn in the model as dashed rings — at the edge offset from both ends of the joint and, on a long joint, in between, no more than the step apart. The edge offset and the step can be changed right in the panel; the suggestions follow. Mark the places you want — click them in the model, or tick them in the list (**Усі** / **Жодного**) — and press **Додати**: one undo step. Marked places are orange, installed ones green; a place next to an installed fastener is shown as taken. In fastener mode a click on a panel adds it to the selection or removes it, `Esc` clears the marks. A joint that breaks a constraint of the fastener gets no suggestions, and the panel says why. **Прибрати** removes the fasteners from the selected panels and their partners. Holes are drawn in the viewport at their real size, on the side of the panel they belong to (Board Studio ▸ Show Holes): a hole whose opening is visible is solid; one inside — in the joint, or opening on the far side of its panel — is dashed, with its depth outlined; one behind another panel is not drawn. In the X-ray and wireframe styles nothing hides holes, they are dashed instead. The **Показувати кріплення в моделі** switch in the panel keeps the holes and the suggestions in view all the time (**Постійно**) or only while the fastener mode is active (**Лише в режимі**); it is remembered between sessions.
- **Settings (Налаштування…)**: the library of fasteners and edge bands, shared by all documents.
  - A fastener has: the offset from the joint ends, the largest and the smallest step between fasteners, the shortest joint; constraints — the least thickness of the panel with the edge and of the other panel, the least wall left beside a hole; and a table of drillings. Each drilling says where it goes (the edge of the panel, the other panel's face at the joint, its outer face, or the panel's own inner face), its diameter and depth (0 — through), the shift towards the middle of the joint, the distance from the edge (for the inner face), the Viyar article, the ABF group and, optionally, the DXF layer.
  - Next to the fields there is a live drawing. Two panels are shown as a section of the joint and as a view of panel A: every hole carries its table row number, diameter and depth, and the shift along the joint and the distance from the edge are dimensioned. A third drawing shows the fasteners spaced along a joint. Clicking a hole or a dimension moves to its field; the focused field highlights its dimension, and the hole's section is brought forward. The panel thicknesses and the joint length next to the drawings are only for the preview. If the fastener does not suit those thicknesses, the reason is shown.
  - An edge band has a name, a thickness, a highlight colour and an article.
  - Defaults: dowel 8×30, confirmat 7×50, minifix with a dowel (drilled as in the ABF samples), and PVC bands 0.4 / 0.8 / 1 / 2 mm. **Типові** restores them.
- **Export DXF for ViyarPro**: writes the selected panels (or all visible panels when none is selected) in the `ABF_Flatten` format that ViyarPro imports (see `viyar/dfx/FORMAT.md`): panels grouped by material, laid out flat with the texture along Y (the orientation alone carries the texture direction; the ABF triangle-and-rhombus label is not drawn), the cut contour inset by the edge banding, edge-banding marks and the holes.

## Installation

### Method 1: Install Script (Linux)

```bash
./scripts/install.sh          # symlink (development: changes apply after restarting IngeTrazo)
./scripts/install.sh --copy   # copy
```

### Method 2: Manual Installation

Copy the `board_studio/` directory into your IngeTrazo extensions folder (**Extensions** > **Open extensions folder**):

- **Linux (Flatpak)**:
  ```text
  ~/.var/app/com.ingetrazo.IngeTrazo/data/ingetrazo/plugins/
  ```
- **Linux**:
  ```text
  ~/.local/share/ingetrazo/plugins/
  ```
- **Windows**:
  ```text
  %APPDATA%\ingetrazo\plugins\
  ```

Restart IngeTrazo after copying.

## Usage

Access the tools via:
- **Extensions Menu**: `Extensions` > `Board Studio` > `New 3-Point Panel` / `Next 3-Point Panel` / `Panel Properties…` / `Кріплення` / `Крайка` / `Export DXF for ViyarPro…` / `Show Holes` / `Налаштування…`
- **Toolbar**: `Panel Creator` toolbar icons
- **Context menu**: right-click a selected panel (or a group of panels)

Drawing a panel:
1. Click the first corner.
2. Click the second point (length), or type the length and press Enter.
3. Click the third point (height), or type the height and press Enter.

While setting the height:
- The direction snaps to the X/Y/Z axes within 3°.
- Arrow keys lock an axis.
- Snaps to points of the model (endpoints, midpoints, edges) work as usual.
- `Esc` cancels.

Panel axes: X runs along the length (1st → 2nd point), Z along the thickness (the push direction), Y = Z × X. The edges are numbered from the panel's corner: **Length edge 1** (Y = 0), **Width edge 2** (X = L), **Length edge 2** (Y = W), **Width edge 1** (X = 0). The axes are stored in the group, so they follow Move and Rotate. Panels made with an older version get their axes from the geometry.

## Customization

- **Boards**: add a line to `PRESETS` in `board_studio/materials.py` (name, thickness in mm, edge texture).
- **Textures**: `board_studio/textures/` holds `oak.png`, `chipboard.png` and `fibreboard.png`. They are seamless textures generated by `scripts/make_textures.py`. Replace them with photos of real samples if you like, keeping the file names. Tile sizes are set in `SURFACES` in `board_studio/materials.py`.

## Development

| File | Purpose |
|---|---|
| `board_studio/__init__.py` | `setup(app)`: menu, toolbar, parameters dialog, saved settings |
| `board_studio/tool.py` | geometry, the 3-point tool, preview, panel creation |
| `board_studio/materials.py` | board presets, face and edge textures |
| `board_studio/panels.py` | panel axes and size, properties, repainting, undo command |
| `board_studio/joints.py` | joint detection (an edge lying on a face) |
| `board_studio/library.py` | the library of fasteners and edge bands (settings, defaults) |
| `board_studio/fasteners.py` | suggested places for a fastener, its drillings, constraints |
| `board_studio/fastenmode.py` | fastener mode: click a suggested place to mark it, click a panel to select it |
| `board_studio/edgeband.py` | edge-banding mode: click an edge to add / remove, highlight |
| `board_studio/settings.py` | the settings window (library editor) |
| `board_studio/dxf.py` | DXF writer for ViyarPro (`ABF_Flatten`), no IngeTrazo dependencies |
| `board_studio/abf_template.dxf` | service sections of an ABF file the export writes into (`scripts/make_dxf_template.py`) |
| `board_studio/ui.py` | properties dialog, fasteners panel (suggestions, marks, Add) and edge-band panel, DXF export, hole marks |
| `board_studio/textures/`, `icons/` | images (`scripts/make_textures.py`, `scripts/make_icons.py`) |

Run the tests with IngeTrazo's own Python (Flatpak, no window):

```bash
./scripts/test.sh
```

`tests/test_dxf.py` needs no IngeTrazo (`python3 tests/test_dxf.py`): it rebuilds a sample from `viyar/dfx/` and compares the geometry. If `ezdxf` is installed, it also audits the file.
