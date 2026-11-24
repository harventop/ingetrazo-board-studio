"""Шаблон DXF для експорту у ViyarPro: файл ABF без геометрії.

Беремо зразок ``viyar/dfx/texture-flatten.dxf`` (його записав SketchUp з ABF) і
лишаємо все службове дослівно: HEADER, CLASSES, таблиці, OBJECTS (матеріали
``ABF_Top_Faces``/``ByBlock``, стилі, layout-и). Прибираємо блоки й сутності
деталей, їхні BLOCK_RECORD, шари, крім «0» і Defpoints, і посилання на
видалене. Результат — ``board_studio/abf_template.dxf``; у нього
``board_studio/dxf.py`` вписує свої шари, блоки й сутності.

    python3 scripts/make_dxf_template.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "viyar" / "dfx" / "texture-flatten.dxf"
OUT = ROOT / "board_studio" / "abf_template.dxf"
KEEP_BLOCKS = {"*Model_Space", "*Paper_Space", "*Paper_Space0", "_ArchTick"}
KEEP_LAYERS = {"0", "Defpoints"}


def pairs(path):
    lines = path.read_text(encoding="latin-1").splitlines()
    return [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]


def records(ps):
    """Розбити на записи за кодом 0 (кожен — список пар)."""
    out = []
    for code, value in ps:
        if code.strip() == "0":
            out.append([])
        out[-1].append((code, value))
    return out


def get(rec, code):
    for c, v in rec:
        if c.strip() == str(code):
            return v
    return None


def drop_group(rec, name):
    """Прибрати групу ``102 {name … 102 }``."""
    out, skip = [], False
    for c, v in rec:
        if c.strip() == "102" and v == "{" + name:
            skip = True
            continue
        if skip:
            if c.strip() == "102" and v == "}":
                skip = False
            continue
        out.append((c, v))
    return out


def main():
    recs = records(pairs(SRC))
    out, section, block = [], None, None
    for rec in recs:
        kind = rec[0][1]
        if kind == "SECTION":
            section = get(rec, 2)
        elif kind == "BLOCK":
            block = get(rec, 2)
        if section == "TABLES":
            if kind == "LAYER" and get(rec, 2) not in KEEP_LAYERS:
                continue
            if kind == "BLOCK_RECORD":
                if get(rec, 2) not in KEEP_BLOCKS:
                    continue
                rec = drop_group(rec, "BLKREFS")
            if kind == "DIMSTYLE":
                rec = drop_group(rec, "ACAD_REACTORS")
        if section == "BLOCKS" and kind != "SECTION" and kind != "ENDSEC" \
                and block not in KEEP_BLOCKS:
            continue
        if section == "ENTITIES" and kind not in ("SECTION", "ENDSEC"):
            continue
        out.append(rec)
    text = "".join(f"{c}\n{v}\n" for rec in out for c, v in rec)
    OUT.write_text(text, encoding="ascii")
    print("wrote", OUT, len(text), "bytes")


if __name__ == "__main__":
    main()
