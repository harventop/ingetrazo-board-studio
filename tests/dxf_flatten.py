"""Мінімальний читач DXF для тестів: розгортає вкладені INSERT і повертає
сутності у світових координатах (з назвами груп-предків з атрибутів).
Залежностей немає: працює і в Python IngeTrazo, і в системному."""
from __future__ import annotations

import math


def read_pairs(path):
    with open(path, encoding="latin-1") as fh:
        lines = fh.read().splitlines()
    return [(int(lines[i].strip()), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]


def sections(pairs):
    out, i = {}, 0
    while i < len(pairs):
        if pairs[i] == (0, "SECTION"):
            name, j, body = pairs[i + 1][1], i + 2, []
            while pairs[j] != (0, "ENDSEC"):
                body.append(pairs[j])
                j += 1
            out[name] = body
            i = j
        i += 1
    return out


def records(body):
    out = []
    for code, value in body:
        if code == 0:
            out.append([value, []])
        elif out:
            out[-1][1].append((code, value))
    return out


def _f(tags, code, default=0.0):
    for c, v in tags:
        if c == code:
            return float(v)
    return default


def _s(tags, code, default=None):
    for c, v in tags:
        if c == code:
            return v
    return default


def ocs_axes(n):
    """Arbitrary axis algorithm: (Ax, Ay, N) для нормалі n."""
    n = _unit(n)
    if abs(n[0]) < 1 / 64 and abs(n[1]) < 1 / 64:
        ax = _cross((0.0, 1.0, 0.0), n)
    else:
        ax = _cross((0.0, 0.0, 1.0), n)
    ax = _unit(ax)
    return ax, _unit(_cross(n, ax)), n


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    l = math.sqrt(sum(x * x for x in a))
    return tuple(x / l for x in a)


def _ocs_to_wcs(p, n):
    ax, ay, az = ocs_axes(n)
    return tuple(p[0] * ax[i] + p[1] * ay[i] + p[2] * az[i] for i in range(3))


def _mat_mul(a, b):   # 3x4 афінні: (R, t)
    ra, ta = a
    rb, tb = b
    r = [[sum(ra[i][k] * rb[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    t = [sum(ra[i][k] * tb[k] for k in range(3)) + ta[i] for i in range(3)]
    return r, t


def _apply(m, p):
    r, t = m
    return tuple(sum(r[i][k] * p[k] for k in range(3)) + t[i] for i in range(3))


def _apply_vec(m, v):
    r, _t = m
    return tuple(sum(r[i][k] * v[k] for k in range(3)) for i in range(3))


IDENTITY = ([[1, 0, 0], [0, 1, 0], [0, 0, 1]], [0, 0, 0])


def insert_matrix(tags):
    n = (_f(tags, 210, 0), _f(tags, 220, 0), _f(tags, 230, 1))
    ins = (_f(tags, 10), _f(tags, 20), _f(tags, 30))
    sx, sy, sz = _f(tags, 41, 1), _f(tags, 42, 1), _f(tags, 43, 1)
    a = math.radians(_f(tags, 50))
    ax, ay, az = ocs_axes(n)
    c, s = math.cos(a), math.sin(a)
    # блок: масштаб → поворот навколо Z в OCS → OCS→WCS; точка вставки — в OCS
    rot = [[c * sx, -s * sy, 0], [s * sx, c * sy, 0], [0, 0, sz]]
    ocs = [[ax[i], ay[i], az[i]] for i in range(3)]
    r = [[sum(ocs[i][k] * rot[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return r, list(_ocs_to_wcs(ins, n))


class Flat:
    """Сутність у світових координатах."""

    def __init__(self, kind, layer, path, **kw):
        self.kind, self.layer, self.path = kind, layer, path
        self.__dict__.update(kw)

    def __repr__(self):
        return f"Flat({self.kind}, {self.layer}, {self.path[-1] if self.path else ''})"


def load(path):
    s = sections(read_pairs(path))
    blocks, cur = {}, None
    for kind, tags in records(s["BLOCKS"]):
        if kind == "BLOCK":
            cur = blocks.setdefault(_s(tags, 2), [])
        elif kind == "ENDBLK":
            cur = None
        elif cur is not None:
            cur.append((kind, tags))
    out = []
    _walk(records(s["ENTITIES"]), blocks, IDENTITY, [], out)
    return out, blocks, s


def _group_entities(recs):
    """INSERT + його ATTRIB-и; POLYLINE + VERTEX-и."""
    i = 0
    while i < len(recs):
        kind, tags = recs[i]
        sub = []
        if kind in ("INSERT", "POLYLINE"):
            j = i + 1
            while j < len(recs) and recs[j][0] in ("ATTRIB", "VERTEX"):
                sub.append(recs[j])
                j += 1
            if j < len(recs) and recs[j][0] == "SEQEND":
                j += 1
            i = j
        else:
            i += 1
        yield kind, tags, sub


def _walk(recs, blocks, m, path, out):
    for kind, tags, sub in _group_entities(recs):
        layer = _s(tags, 8, "0")
        if kind == "INSERT":
            name = _s(tags, 2)
            attrs = {_s(t, 2): _s(t, 1) for k, t in sub if k == "ATTRIB"}
            label = attrs.get("Skp_GroupInstanceName") or attrs.get("Skp_ComponentInstanceName") or name
            _walk(blocks.get(name, []), blocks, _mat_mul(m, insert_matrix(tags)),
                  path + [label], out)
            out.append(Flat("INSERT", layer, path, block=name, label=label))
        elif kind == "CIRCLE":
            n = (_f(tags, 210, 0), _f(tags, 220, 0), _f(tags, 230, 1))
            c = _ocs_to_wcs((_f(tags, 10), _f(tags, 20), _f(tags, 30)), n)
            nw = _unit(_apply_vec(m, n))
            out.append(Flat("CIRCLE", layer, path, center=_apply(m, c), normal=nw,
                            radius=_f(tags, 40)))
        elif kind == "LINE":
            out.append(Flat("LINE", layer, path,
                            points=[_apply(m, (_f(tags, 10), _f(tags, 20), _f(tags, 30))),
                                    _apply(m, (_f(tags, 11), _f(tags, 21), _f(tags, 31)))]))
        elif kind == "POLYLINE":
            flags = int(_f(tags, 70))
            verts = [t for k, t in sub if k == "VERTEX"]
            if flags & 64:
                pts = [_apply(m, (_f(t, 10), _f(t, 20), _f(t, 30))) for t in verts
                       if int(_f(t, 70)) & 64]
                faces = [[abs(int(_f(t, c))) - 1 for c in (71, 72, 73, 74) if int(_f(t, c))]
                         for t in verts if int(_f(t, 70)) & 128 and not int(_f(t, 70)) & 64]
                out.append(Flat("POLYFACE", layer, path, points=pts, faces=faces,
                                color=int(_f(tags, 62, 256))))
            else:
                pts = [_apply(m, (_f(t, 10), _f(t, 20), _f(t, 30))) for t in verts]
                out.append(Flat("POLYLINE", layer, path, points=pts, closed=bool(flags & 1)))
        elif kind == "DIMENSION":
            out.append(Flat("DIMENSION", layer, path, text=_s(tags, 1)))
        else:
            out.append(Flat(kind, layer, path))
