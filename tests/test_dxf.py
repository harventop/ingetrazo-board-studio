"""Експорт DXF для ViyarPro: відтворюємо зразок ABF і порівнюємо геометрію.

Без IngeTrazo: ``python3 tests/test_dxf.py`` (або ./scripts/test.sh).
Якщо встановлено ezdxf — ще й перевіряє файл його аудитом.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SAMPLES = PROJECT / "viyar" / "dfx"
sys.path.insert(0, str(Path(__file__).parent))
import dxf_flatten as F                                     # noqa: E402

_spec = importlib.util.spec_from_file_location("bs_dxf", PROJECT / "board_studio" / "dxf.py")
D = importlib.util.module_from_spec(_spec)
sys.modules["bs_dxf"] = D
_spec.loader.exec_module(D)

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print("FAIL:", msg)


def r(v):
    return round(v + 0.0, 2) + 0.0


def summary(path):
    """Для кожної деталі (у порядку розкладки справа наліво): розмір і
    вміст відносно її лівого нижнього кута."""
    ents, _blocks, _s = F.load(path)
    out = []
    tops = [e for e in ents if e.kind == "POLYFACE" and e.color == 7]
    for top in sorted(tops, key=lambda e: -max(p[0] for p in e.points)):
        x0 = min(p[0] for p in top.points)
        y0 = min(p[1] for p in top.points)
        x1 = max(p[0] for p in top.points)
        y1 = max(p[1] for p in top.points)
        mine = [e for e in ents if e.kind in ("CIRCLE", "POLYLINE")
                and _inside(e, x0 - 1, y0 - 1, x1 + 1, y1 + 1)]

        def rel(p):
            return (r(p[0] - x0), r(p[1] - y0), r(p[2]))
        circles = sorted((e.layer, rel(e.center), r(e.radius), tuple(abs(r(c)) for c in e.normal))
                         for e in mine if e.kind == "CIRCLE")
        polys = sorted((e.layer, tuple(sorted(rel(p) for p in e.points[:-1])))
                       for e in mine if e.kind == "POLYLINE"
                       and e.layer not in ("ABF_edgeBanding", "ABF_Label"))
        bands = sorted(_band_side(e, x0, y0, x1, y1) for e in mine
                       if e.kind == "POLYLINE" and e.layer == "ABF_edgeBanding")
        labels = sum(1 for e in mine if e.kind == "POLYLINE" and e.layer == "ABF_Label")
        out.append({"size": (r(x1 - x0), r(y1 - y0)), "circles": circles, "polys": polys,
                    "bands": bands, "labels": labels})
    return out, ents


def _inside(e, x0, y0, x1, y1):
    pts = [e.center] if e.kind == "CIRCLE" else e.points
    return all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in pts)


def _band_side(e, x0, y0, x1, y1):
    """Сторона, на яку вказує вершина трикутника кромки (найближча до краю)."""
    tip = e.points[0]
    d = [tip[1] - y0, x1 - tip[0], y1 - tip[1], tip[0] - x0]
    return d.index(min(d))


def sample_parts():
    """Деталі зі зразка «300x500+200-конфірмат+кромка» у локальних осях."""
    a = D.Part("Shelf", 300, 200, 16, edges=(0.8, 0, 0, 0.8), grain="none", holes=[
        D.Hole("face", 37, 192, 7, None, top=False, article="44817", group="_ABF_screwInside"),
        D.Hole("face", 263, 192, 7, None, top=False, article="44817", group="_ABF_screwInside")])
    b = D.Part("Side", 500, 300, 16, edges=(0, 0, 0.8, 0), grain="none", holes=[
        D.Hole("side", 0, 263, 4.5, 34, side=3),
        D.Hole("side", 0, 37, 4.5, 34, side=3)])
    return [a, b]


def test_against_sample():
    sample, _ = summary(SAMPLES / "300x500+200-конфірмат+кромка-flatten.dxf")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.dxf"
        D.export(sample_parts(), path)
        mine, ents = summary(path)
        text = path.read_text(encoding="ascii")
        _validate_with_ezdxf(path)
    check(len(mine) == len(sample) == 2, f"two panels: {len(mine)}")
    for got, want in zip(mine, sample):
        for key in ("size", "circles", "polys", "bands", "labels"):
            check(got[key] == want[key], f"{key}: {got[key]} != {want[key]}")
    check("AC1021" in text and "ANSI_1252" in text, "R2007 header")
    names = [e for e in ents if e.kind == "INSERT"]
    check(any(e.block == "THICKNESS_16" and e.label == "ABF_Flatten" for e in names),
          "material block THICKNESS_16 with ABF_Flatten attribute")
    check(sum(1 for e in ents if e.kind == "DIMENSION" and e.text == "THICKNESS_16") == 1,
          "material caption")


def test_grain_and_names():
    """Текстура вздовж довжини → довжина лягає вздовж Y; мітки ABF_Label немає;
    назва блоку матеріалу з артикулом; кирилиця → «_»."""
    parts = [D.Part("Фасад", 700, 400, 18, grain="length", article="$151932",
                    decor="KRONOSPAN 5307 SN"),
             D.Part("Полиця", 700, 400, 18, grain="width", article="151932",
                    decor="KRONOSPAN 5307 SN"),
             D.Part("Задня", 700, 400, 16)]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.dxf"
        D.export(parts, path)
        got, ents = summary(path)
        path_text = path.read_text(encoding="ascii")
        _validate_with_ezdxf(path)
    check([g["size"] for g in got] == [(400.0, 700.0), (700.0, 400.0), (400.0, 700.0)],
          f"orientation by grain: {[g['size'] for g in got]}")
    check([g["labels"] for g in got] == [0, 0, 0], f"no grain labels {[g['labels'] for g in got]}")
    check("ABF_Label" not in path_text, "no ABF_Label layer")
    blocks = {e.block for e in ents if e.kind == "INSERT" and e.label == "ABF_Flatten"}
    check("$151932____KRONOSPAN_5307_SN__THICKNESS_18" in blocks, f"material block: {blocks}")
    check("THICKNESS_16" in blocks, "plain block")
    panels = [e.label for e in ents if e.kind == "INSERT" and len(e.path) == 1
              and e.path[0] == "ABF_Flatten" and e.block.startswith("Group")]
    check(set(panels) == {"_____", "______"}, f"panel names {panels}")
    check(D.dxf_name("ДСП 16 (білий)") == "____16________", D.dxf_name("ДСП 16 (білий)"))
    check(D.face_layer(D.Hole("face", 0, 0, 8, 12, article="38878")) == "D8-DEPTH12-$38878",
          "face layer")
    check(D.side_layer(D.Hole("side", 0, 0, 4.5, 34)) == "Dside4.5", "side layer")


def test_abf_structure():
    """Як у файлах ABF: службові секції з шаблону, верхня грань бруска —
    з матеріалом ABF_Top_Faces, решта — ByBlock; посилання цілі."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.dxf"
        D.export(sample_parts(), path)
        pairs = F.read_pairs(path)
        raw = path.read_bytes()
    check(b"\r\n" in raw, "CRLF line endings, as ABF")
    s = F.sections(pairs)
    mats = {dict(t)[5]: dict(t).get(1) for k, t in F.records(s["OBJECTS"]) if k == "MATERIAL"}
    check("ABF_Top_Faces" in mats.values(), f"template materials {mats}")
    faces = [(dict(t).get(62), mats.get(dict(t).get(347))) for k, t in F.records(s["BLOCKS"])
             if k == "POLYLINE" and dict(t).get(70) == "64"]
    check(len(faces) == 12, f"12 box faces: {len(faces)}")
    check(sorted(faces) == [("0", "ByBlock")] * 10 + [("7", "ABF_Top_Faces")] * 2,
          f"face materials {sorted(faces)}")
    defined = [v for name, body in s.items() if name != "HEADER"
               for c, v in body if c in (5, 105)]
    check(len(defined) == len(set(defined)), "unique handles")
    dangling = {(c, v) for c, v in pairs if c in (330, 331, 340, 347, 348, 350, 360, 390)
                and v != "0" and v not in set(defined)}
    check(not dangling, f"dangling references {sorted(dangling)[:5]}")
    seed = [pairs[i + 1][1] for i, (c, v) in enumerate(pairs) if v == "$HANDSEED"]
    check(seed and int(seed[0], 16) > max(int(h, 16) for h in defined), f"handseed {seed}")
    layers = [dict(t)[2] for k, t in F.records(s["TABLES"]) if k == "LAYER"]
    for layer in ("0", "Defpoints", "ABF_cuttingLines", "ABF_edgeBanding", "Dside4.5",
                  "D7-DEPTHF-$44817"):
        check(layer in layers, f"layer {layer} declared")


def _structure(path, owner_name):
    """Сутності файлу без координат і ручок: (секція, [(код, значення)])."""
    out = []
    for name, body in F.sections(F.read_pairs(path)).items():
        if name not in ("BLOCKS", "ENTITIES"):
            continue
        for kind, tags in F.records(body):
            rec = [name, kind]
            for code, value in tags:
                value = value.strip()
                if code in (5, 105) or 320 <= code <= 369:
                    value = "H"
                elif 10 <= code <= 59 or code in (1011, 1021, 1031):
                    value = "X"
                elif code in (2, 3) and value.startswith(("Group", "*D")):
                    value = "NAME"
                elif code == 1 and value == owner_name:
                    value = ""
                rec.append((code, value))
            out.append(tuple(rec))
    return out


def _drawing(path):
    """Геометрія в порядку запису, з локальними координатами блоків (2 знаки)."""
    out = []
    for kind, tags in F.records(F.sections(F.read_pairs(path))["BLOCKS"]):
        d = dict(tags)
        if d.get(8) == "Defpoints" or (370, "-2") in [(c, v.strip()) for c, v in tags]:
            continue
        if kind in ("VERTEX", "LINE", "INSERT"):
            out.append((kind, d.get(8)) + tuple(r(float(d[c])) for c in (10, 20, 30, 11, 21, 31)
                                                if c in d))
    return out


def _edge_marks(path):
    ents, _b, _s = F.load(path)
    return sorted(tuple(tuple(r(c) for c in p) for p in e.points)
                  for e in ents if e.kind == "POLYLINE" and e.layer == "ABF_edgeBanding")


def test_against_origin():
    """Панель 500×500×18 з крайкою 1 мм: ті самі сутності й поля в тому самому
    порядку, що в ABF, і ті самі позначки крайки."""
    origin = PROJECT / "viyar" / "diff" / "origin.dxf"
    part = D.Part("Panel 1", 500, 500, 18, edges=(1, 1, 1, 1))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.dxf"
        D.export([part], path)
        got, want = _structure(path, "Panel_1"), _structure(origin, "Panel_1")
        check(_drawing(path) == _drawing(origin), "same vertices in the same order as ABF")
        marks, tables = _edge_marks(path), F.sections(F.read_pairs(path))["TABLES"]
    # ABF виносить довгий підпис убік, тоді в *D є зайва лінія-виноска.
    extra = [i for i, e in enumerate(want) if e[1] == "LINE" and (370, "-2") in e[2:]][2]
    del want[extra]
    check(len(got) == len(want), f"entity count {len(got)} != {len(want)}")
    for a, b in zip(got, want):
        if a != b:
            check(False, f"entity fields {a} != {b}")
            break
    check(marks == _edge_marks(origin), f"edge marks {marks}")
    for table, less in (("LAYER", 0), ("BLOCK_RECORD", 2)):
        recs = F.records(tables)
        head = [dict(t) for k, t in recs if k == "TABLE" and dict(t).get(2) == table][0]
        n = sum(k == table for k, _t in recs)
        check(int(head[70]) == n - less, f"{table}: declared {head[70]}, records {n}")


def test_flip():
    """Глухі отвори на нижній грані → деталь перевертається ними догори, як в
    ABF. Відтворюємо «дві панелі міксфіксом і шкантом.dxf» (усі отвори — знизу)."""
    sample, _ = summary(PROJECT / "viyar" / "diff" / "дві панелі міксфіксом і шкантом.dxf")
    side = [(37, 33), (69, 25), (463, 33), (431, 25)]
    base = [(37, 5), (69, 8), (463, 5), (431, 8)]
    # У локальних осях деталі Y дзеркальний до розкладки: вона лежить низом догори.
    parts = [
        D.Part("Base", 500, 500, 18, grain="width", holes=[
            D.Hole("face", 491, 500 - y, d, 12, top=False, layer="D8-DEPTH12-$38878",
                   group="_ABF_minifixPlasticBase") for y, d in base]),
        D.Part("Bolt", 500, 500, 18, grain="width", holes=[
            D.Hole("side", 0, 500 - y, 8, depth, side=3) for y, depth in side] + [
            D.Hole("face", 34, 500 - y, 15, 13.8, top=False, article="61281",
                   group="_ABF_minifixBolts") for y in (37, 463)])]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.dxf"
        D.export(parts, path)
        mine, _ = summary(path)
        _validate_with_ezdxf(path)
    check(len(mine) == len(sample) == 2, f"two panels: {len(mine)}")
    for got, want in zip(mine, sample):
        for key in ("size", "circles", "polys", "bands"):
            check(got[key] == want[key], f"flip {key}: {got[key]} != {want[key]}")

    def hole(depth, top):
        return D.Hole("face", 50, 60, 8, depth, top=top)

    def flips(*holes):
        return D.flipped(D.Part("P", 700, 400, 18, holes=list(holes)))
    check(not flips(), "no holes: as is")
    check(not flips(hole(12, True)), "top hole: as is")
    check(flips(hole(12, False), hole(None, True)), "through holes do not count")
    check(not flips(hole(None, False), hole(18, False)), "only through holes: as is")
    check(not flips(hole(12, True), hole(12, False)), "both faces equally: as is")
    check(flips(hole(12, True), hole(12, False), hole(13, False)), "more holes below: flip")

    # Обертання, а не дзеркало: крайка й отвір лишаються біля того самого кута,
    # сторона під отвором обходиться у зворотний бік.
    for grain in ("length", "width"):
        p = D.Placed(D.Part("P", 700, 400, 18, edges=(1, 2, 3, 4), grain=grain,
                            holes=[hole(12, False), D.Hole("side", 0, 60, 8, 25, side=3, z=5)]))
        X, Y = p.point(0, 60)                       # точка на локальній стороні 3
        near = {0: Y, 1: p.a - X, 2: p.b - Y, 3: X}
        check(near[p.side(3)] == 0, f"{grain}: side 3 -> {p.side(3)} at {(X, Y)}")
        check(p.edges[p.side(3)] == 4, f"{grain}: edge thickness follows its side")
        step = (p.side(1) - p.side(0)) % 4
        check(step == 3, f"{grain}: turned over, not mirrored ({step})")
        check(p.height(p.part.holes[1]) == 13, f"{grain}: side hole height")
        check(p.top(p.part.holes[0]), f"{grain}: the hole is on top")


def test_edge_mark_sizes():
    for a, b, h, gap in ((200, 300, 17.978058, 2.568294), (300, 500, 25.918367, 4.319728),
                         (500, 500, 35.398582, 7.079716)):
        got = D.mark_size(a, b)
        check(abs(got[0] - h) < 1e-4 and abs(got[1] - gap) < 1e-4, f"mark {a}x{b}: {got}")


def _validate_with_ezdxf(path):
    try:
        from ezdxf import recover
    except ImportError:
        return
    _doc, auditor = recover.readfile(str(path))
    check(not auditor.errors and not auditor.fixes,
          f"ezdxf audit: {[str(e) for e in auditor.errors + auditor.fixes][:5]}")


def main():
    test_against_sample()
    test_grain_and_names()
    test_abf_structure()
    test_against_origin()
    test_flip()
    test_edge_mark_sizes()
    if FAILS:
        sys.exit(f"\n{len(FAILS)} failure(s)")
    print("OK (dxf)")


if __name__ == "__main__":
    main()
